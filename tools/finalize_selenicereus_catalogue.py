"""Fusionne le fichier de staging Selenicereus dans le Cactaceae canonique.

Le générateur de recherche écrit volontairement un fichier de staging afin de
ne jamais écraser le catalogue Cactaceae existant. Cette étape finale fusionne
les fiches par nom scientifique puis supprime le staging, ce qui respecte la
règle d'un seul fichier JSON par famille.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILIES_DIR = ROOT / "familles_plantes"
CANONICAL_FILE = FAMILIES_DIR / "cactaceae.json"
STAGING_FILE = FAMILIES_DIR / "cactaceae_selenicereus.json"


def _load(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path} doit contenir une liste JSON")
    return [item for item in payload if isinstance(item, dict)]


def _scientific(profile: dict) -> str:
    taxonomy = profile.get("taxonomie")
    if not isinstance(taxonomy, dict):
        return ""
    return str(taxonomy.get("nom_scientifique") or "").strip()


def merge_staging() -> int:
    """Fusionne le staging et retourne le nombre total de fiches traitées."""
    if not STAGING_FILE.exists():
        return 0

    canonical = _load(CANONICAL_FILE)
    staged = _load(STAGING_FILE)
    by_name = {_scientific(profile): index for index, profile in enumerate(canonical) if _scientific(profile)}

    for profile in staged:
        name = _scientific(profile)
        if not name:
            continue
        existing = by_name.get(name)
        if existing is None:
            by_name[name] = len(canonical)
            canonical.append(profile)
        else:
            # Les fiches générées peuvent être régénérées avec une provenance
            # plus récente ; le staging devient alors la source de vérité.
            canonical[existing] = profile

    canonical.sort(key=lambda profile: _scientific(profile).casefold())
    CANONICAL_FILE.write_text(json.dumps(canonical, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STAGING_FILE.unlink()
    return len(staged)


def main() -> int:
    merged = merge_staging()
    print(f"Cactaceae fusionné : {merged} fiches de staging traitées.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
