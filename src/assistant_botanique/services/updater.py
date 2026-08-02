"""Vérification, téléchargement et lancement des mises à jour GitHub Releases."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from packaging.version import InvalidVersion, Version

from assistant_botanique import __version__

API_URL = "https://api.github.com/repos/LaurentCOLL1/Assistant_Botanique/releases?per_page=30"
RELEASES_URL = "https://github.com/LaurentCOLL1/Assistant_Botanique/releases"
USER_AGENT = "AssistantBotanique-Updater"


@dataclass(slots=True)
class UpdateInfo:
    current: str
    latest: str
    available: bool
    release_url: str
    notes: str
    published: bool = True
    asset_name: str = ""
    asset_url: str = ""
    asset_digest: str = ""
    asset_size: int = 0
    prerelease: bool = False

    @property
    def directly_installable(self) -> bool:
        return bool(self.asset_url and self.asset_name.casefold().endswith(".exe"))


def _normalized_version_text(value: str) -> str:
    text = str(value or "").strip().lstrip("vV")
    substitutions = (
        (r"(?i)[._-]?alpha[._-]?(\d+)", r"a\1"),
        (r"(?i)[._-]?beta[._-]?(\d+)", r"b\1"),
        (r"(?i)[._-]?preview[._-]?(\d+)", r"b\1"),
        (r"(?i)[._-]?rc[._-]?(\d+)", r"rc\1"),
    )
    for pattern, replacement in substitutions:
        text = re.sub(pattern, replacement, text)
    return text


def _version(value: str) -> Version:
    try:
        return Version(_normalized_version_text(value))
    except InvalidVersion:
        return Version("0")


def _choose_windows_asset(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    executable = [item for item in assets if str(item.get("name") or "").casefold().endswith(".exe")]
    if not executable:
        return None

    def score(item: dict[str, Any]) -> tuple[int, int]:
        name = str(item.get("name") or "").casefold()
        preferred = any(word in name for word in ("setup", "installer", "installation"))
        undesirable = any(word in name for word in ("portable", "debug", "symbols"))
        return (2 if preferred else 0) - (2 if undesirable else 0), int(item.get("size") or 0)

    return max(executable, key=score)


def _request_json(url: str, timeout: float) -> Any:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _select_release(payload: Any) -> dict[str, Any] | None:
    releases = payload if isinstance(payload, list) else [payload]
    candidates: list[dict[str, Any]] = []
    for item in releases:
        if not isinstance(item, dict) or bool(item.get("draft")):
            continue
        tag = str(item.get("tag_name") or "").strip()
        if not tag or _version(tag) == Version("0"):
            continue
        candidates.append(item)
    if not candidates:
        return None
    return max(candidates, key=lambda item: _version(str(item.get("tag_name") or "0")))


def check_for_update(timeout: float = 5.0) -> UpdateInfo:
    try:
        payload = _request_json(API_URL, timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return UpdateInfo(
                current=__version__,
                latest=__version__,
                available=False,
                release_url=RELEASES_URL,
                notes="Aucune version n'a encore été publiée dans GitHub Releases.",
                published=False,
            )
        raise RuntimeError(f"GitHub a répondu avec l'erreur HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(f"Connexion à GitHub impossible : {reason}") from exc

    release = _select_release(payload)
    if release is None:
        return UpdateInfo(
            current=__version__,
            latest=__version__,
            available=False,
            release_url=RELEASES_URL,
            notes="Aucune version publiée utilisable n'a été trouvée.",
            published=False,
        )

    latest = str(release.get("tag_name") or "0.0.0").lstrip("vV")
    assets = release.get("assets") if isinstance(release.get("assets"), list) else []
    asset = _choose_windows_asset(assets) or {}
    return UpdateInfo(
        current=__version__,
        latest=latest,
        available=_version(latest) > _version(__version__),
        release_url=str(release.get("html_url") or RELEASES_URL),
        notes=str(release.get("body") or ""),
        published=True,
        asset_name=str(asset.get("name") or ""),
        asset_url=str(asset.get("browser_download_url") or ""),
        asset_digest=str(asset.get("digest") or ""),
        asset_size=int(asset.get("size") or 0),
        prerelease=bool(release.get("prerelease")),
    )


def _safe_asset_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(name).name).strip(" .")
    return cleaned or "AssistantBotanique-Setup.exe"


def download_update(
    info: UpdateInfo,
    *,
    directory: Path | str | None = None,
    timeout: float = 60.0,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    if not info.directly_installable:
        raise RuntimeError("Cette release ne contient pas d'installateur Windows téléchargeable directement.")
    destination_dir = Path(directory) if directory else Path(tempfile.gettempdir()) / "AssistantBotanique" / "updates"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / _safe_asset_name(info.asset_name)
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(info.asset_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, temporary.open("wb") as handle:
            total = int(response.headers.get("Content-Length") or info.asset_size or 0)
            downloaded = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(downloaded, total)
    except (OSError, urllib.error.URLError) as exc:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Téléchargement de la mise à jour impossible : {exc}") from exc
    os.replace(temporary, destination)

    digest = info.asset_digest.strip()
    if digest.casefold().startswith("sha256:"):
        expected = digest.split(":", 1)[1].strip().casefold()
        actual = hashlib.sha256(destination.read_bytes()).hexdigest().casefold()
        if not expected or actual != expected:
            destination.unlink(missing_ok=True)
            raise RuntimeError("Le contrôle SHA-256 de l'installateur a échoué.")
    return destination


def launch_installer(path: Path | str) -> None:
    installer = Path(path)
    if not installer.is_file():
        raise RuntimeError("L'installateur téléchargé est introuvable.")
    if sys.platform != "win32":
        raise RuntimeError("L'installation automatique est actuellement disponible sous Windows uniquement.")
    try:
        subprocess.Popen([str(installer)], close_fds=True)
    except OSError as exc:
        raise RuntimeError(f"Impossible de lancer l'installateur : {exc}") from exc


def download_and_launch_update(
    info: UpdateInfo,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    path = download_update(info, progress=progress)
    launch_installer(path)
    return path
