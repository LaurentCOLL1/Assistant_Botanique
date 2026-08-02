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

from assistant_botanique import __version__

API_URL = "https://api.github.com/repos/LaurentCOLL1/Assistant_Botanique/releases/latest"
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

    @property
    def directly_installable(self) -> bool:
        return bool(self.asset_url and self.asset_name.casefold().endswith(".exe"))


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", value)
    return tuple(int(part) for part in parts[:4]) or (0,)


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


def _request_json(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


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

    latest = str(payload.get("tag_name") or "0.0.0").lstrip("v")
    assets = payload.get("assets") if isinstance(payload.get("assets"), list) else []
    asset = _choose_windows_asset(assets) or {}
    return UpdateInfo(
        current=__version__,
        latest=latest,
        available=_version_tuple(latest) > _version_tuple(__version__),
        release_url=str(payload.get("html_url") or RELEASES_URL),
        notes=str(payload.get("body") or ""),
        published=True,
        asset_name=str(asset.get("name") or ""),
        asset_url=str(asset.get("browser_download_url") or ""),
        asset_digest=str(asset.get("digest") or ""),
        asset_size=int(asset.get("size") or 0),
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
