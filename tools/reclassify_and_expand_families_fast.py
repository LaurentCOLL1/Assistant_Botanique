"""Orchestrateur parallèle du reclassement et de l'enrichissement GBIF."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import reclassify_and_expand_families as base

MAX_WORKERS = 16


def fast_request_json(url: str, params: dict[str, Any]) -> dict[str, Any] | None:
    request = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params),
        headers=base.HEADERS,
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 or (exc.code != 429 and exc.code < 500):
                return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(0.5 + attempt)
    return None


base.request_json = fast_request_json


def resolve_family(profile: dict[str, Any], audited: dict[str, Any]) -> str:
    taxonomic = audited.get("taxonomic", {}) if isinstance(audited, dict) else {}
    fresh = base.match(base.name(profile), "SPECIES") or {}
    return base.clean(fresh.get("family") or taxonomic.get("family"))


def expand_family(
    family_name: str,
    source_items: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[tuple[str, str, str, Any]], int | None]:
    items = list(source_items)
    existing = {base.normalized(base.name(profile)) for profile in items}
    additions: list[tuple[str, str, str, Any]] = []
    ordered: list[tuple[str, str]] = []
    ordered.extend((candidate, "comestible") for candidate in base.EDIBLE.get(family_name, []))
    ordered.extend((candidate, "cultivee") for candidate in base.CULTIVATED.get(family_name, []))

    for scientific_name, priority in ordered:
        if len(items) >= base.TARGET or base.normalized(scientific_name) in existing:
            continue
        candidate = base.verified_candidate(scientific_name, family_name)
        if candidate and base.normalized(candidate["name"]) not in existing:
            items.append(
                base.provisional_profile(
                    base.choose_template(items, candidate["name"]),
                    candidate,
                    priority,
                )
            )
            existing.add(base.normalized(candidate["name"]))
            additions.append((family_name, candidate["name"], priority, candidate.get("key")))

    if len(items) < base.TARGET:
        for candidate in base.gbif_species(family_name):
            if len(items) >= base.TARGET:
                break
            key = base.normalized(candidate["name"])
            if key in existing:
                continue
            items.append(
                base.provisional_profile(
                    base.choose_template(items, candidate["name"]),
                    candidate,
                    "gbif_frequente",
                )
            )
            existing.add(key)
            additions.append((family_name, candidate["name"], "gbif_frequente", candidate.get("key")))

    limitation = len(items) if len(items) < base.TARGET else None
    return family_name, items, additions, limitation


def main() -> int:
    files = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(base.FAMILY_DIR.glob("*.json"))
    }
    originals = set(files)
    audit = (
        json.loads(base.AUDIT.read_text(encoding="utf-8")).get("profiles", {})
        if base.AUDIT.exists()
        else {}
    )

    flagged: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for items in files.values():
        for profile in items:
            audited = audit.get(base.normalized(base.name(profile)), {})
            taxonomic = audited.get("taxonomic", {}) if isinstance(audited, dict) else {}
            if taxonomic.get("status") == "family_mismatch" or taxonomic.get("family_consistent") is False:
                flagged.append((profile, audited, base.family(profile)))

    moves: list[tuple[str, str, str]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="gbif-family") as executor:
        futures = {
            executor.submit(resolve_family, profile, audited): (profile, old_family)
            for profile, audited, old_family in flagged
        }
        for future in as_completed(futures):
            profile, old_family = futures[future]
            new_family = future.result()
            if new_family and new_family.casefold() != old_family.casefold():
                profile.setdefault("taxonomie", {})["famille"] = new_family
                moves.append((base.name(profile), old_family, new_family))

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for items in files.values():
        for profile in items:
            if base.family(profile):
                groups[base.family(profile)].append(profile)

    for family_name, items in list(groups.items()):
        unique: dict[str, dict[str, Any]] = {}
        for profile in items:
            key = base.normalized(base.name(profile))
            previous = unique.get(key)
            previous_sources = len(previous.get("sources", [])) if previous else -1
            current_sources = len(profile.get("sources", []))
            if previous is None or current_sources > previous_sources:
                unique[key] = profile
        groups[family_name] = list(unique.values())

    additions: list[tuple[str, str, str, Any]] = []
    limitations: list[tuple[str, int]] = []
    underfilled = {family_name: items for family_name, items in groups.items() if len(items) < base.TARGET}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="gbif-expand") as executor:
        futures = {
            executor.submit(expand_family, family_name, items): family_name
            for family_name, items in underfilled.items()
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            family_name, items, family_additions, limitation = future.result()
            groups[family_name] = items
            additions.extend(family_additions)
            if limitation is not None:
                limitations.append((family_name, limitation))
            if completed % 10 == 0 or completed == len(futures):
                print(f"Familles enrichies : {completed}/{len(futures)}", flush=True)

    final = {
        base.slug(family_name): sorted(
            items,
            key=lambda profile: (
                1 if isinstance(profile.get("validation_catalogue"), dict) else 0,
                base.name(profile).casefold(),
            ),
        )
        for family_name, items in groups.items()
    }
    for filename, items in final.items():
        (base.FAMILY_DIR / filename).write_text(
            json.dumps(items, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    deleted = sorted(originals - set(final))
    for filename in deleted:
        path = base.FAMILY_DIR / filename
        if path.exists():
            path.unlink()

    lines = [
        "# Reclassement GBIF et enrichissement des familles",
        "",
        f"Généré le {datetime.now(timezone.utc).isoformat(timespec='seconds')}.",
        "",
        "## Résumé",
        "",
        f"- Reclassements : **{len(moves)}**",
        f"- Fichiers consolidés/supprimés : **{len(deleted)}**",
        f"- Espèces ajoutées : **{len(additions)}**",
        f"- Familles à au moins {base.TARGET} espèces : **{sum(len(items) >= base.TARGET for items in groups.values())}/{len(groups)}**",
        f"- Familles restant sous {base.TARGET} : **{len(limitations)}**",
        "",
        "## Reclassements",
        "",
    ]
    lines.extend([f"- **{species}** : {old} → {new}" for species, old, new in sorted(moves)] or ["- Aucun."])
    lines.extend(["", "## Fichiers supprimés ou consolidés", ""])
    lines.extend([f"- `{filename}`" for filename in deleted] or ["- Aucun."])
    lines.extend(["", "## Espèces ajoutées", ""])
    lines.extend(
        [
            f"- **{family_name}** — {species} (`{priority}`, GBIF {key or 'sans clé'})"
            for family_name, species, priority, key in sorted(additions)
        ]
        or ["- Aucune."]
    )
    lines.extend(["", f"## Familles restant sous {base.TARGET} espèces", ""])
    lines.extend([f"- **{family_name}** : {count} espèce(s)" for family_name, count in sorted(limitations)] or ["- Aucune."])
    lines.extend(
        [
            "",
            "## Prudence",
            "",
            "Les identités taxonomiques ajoutées sont validées par GBIF. Les données horticoles copiées depuis une espèce apparentée sont explicitement provisoires et doivent être revues avant toute prescription de culture ou de consommation.",
        ]
    )
    base.REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"moves={len(moves)} deleted={len(deleted)} additions={len(additions)} limitations={len(limitations)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
