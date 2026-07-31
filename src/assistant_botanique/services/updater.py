"""Vérification volontaire des versions publiées sur GitHub Releases."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from assistant_botanique import __version__

API_URL = "https://api.github.com/repos/LaurentCOLL1/Assistant_Botanique/releases/latest"
RELEASES_URL = "https://github.com/LaurentCOLL1/Assistant_Botanique/releases"


@dataclass(slots=True)
class UpdateInfo:
    current: str
    latest: str
    available: bool
    release_url: str
    notes: str
    published: bool = True


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", value)
    return tuple(int(part) for part in parts[:4]) or (0,)


def check_for_update(timeout: float = 5.0) -> UpdateInfo:
    request = urllib.request.Request(
        API_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "AssistantBotanique"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
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
    return UpdateInfo(
        current=__version__,
        latest=latest,
        available=_version_tuple(latest) > _version_tuple(__version__),
        release_url=str(payload.get("html_url") or RELEASES_URL),
        notes=str(payload.get("body") or ""),
        published=True,
    )
