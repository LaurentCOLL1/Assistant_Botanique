"""Vérification volontaire des versions publiées sur GitHub Releases."""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

from assistant_botanique import __version__

API_URL = "https://api.github.com/repos/LaurentCOLL1/Assistant_Botanique/releases/latest"


@dataclass(slots=True)
class UpdateInfo:
    current: str
    latest: str
    available: bool
    release_url: str
    notes: str


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", value)
    return tuple(int(part) for part in parts[:4]) or (0,)


def check_for_update(timeout: float = 5.0) -> UpdateInfo:
    request = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "AssistantBotanique"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    latest = str(payload.get("tag_name") or "0.0.0").lstrip("v")
    return UpdateInfo(
        current=__version__,
        latest=latest,
        available=_version_tuple(latest) > _version_tuple(__version__),
        release_url=str(payload.get("html_url") or ""),
        notes=str(payload.get("body") or ""),
    )
