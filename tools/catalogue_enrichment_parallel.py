"""Exécution parallèle et déterministe de l'audit complet du catalogue."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from typing import Any

import catalogue_enrichment as base
from catalogue_enrichment import (
    PHOTOS_OUTPUT,
    REPORT_OUTPUT,
    TAXONOMY_OUTPUT,
    USER_AGENT,
    build_report,
    family_name,
    find_photo,
    load_profiles,
    profile_id,
    scientific_name,
    structural_audit,
    taxonomic_match,
)

MAX_WORKERS = 20
REQUEST_TIMEOUT = 6
REQUEST_RETRIES = 1


def fast_request_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    retries: int = REQUEST_RETRIES,
) -> Any:
    """Version strictement bornée du client HTTP utilisé par l'audit."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    attempts = min(max(1, retries), REQUEST_RETRIES)
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if (exc.code == 429 or 500 <= exc.code < 600) and attempt + 1 < attempts:
                time.sleep(0.5)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt + 1 >= attempts:
                raise
            time.sleep(0.5)
    return None


base.request_json = fast_request_json


def audit_one(position: int, output_identifier: str, profile: dict) -> tuple[int, str, dict, dict]:
    taxon = taxonomic_match(profile)
    structure = structural_audit(profile)
    photo = find_photo(profile, taxon)
    taxonomy_item = {
        "scientific_name": scientific_name(profile),
        "declared_family": family_name(profile),
        "source_file": profile.get("_source_file"),
        "source_index": profile.get("_source_index"),
        "structure": structure,
        "taxonomic": taxon,
        "reviewed_at": date.today().isoformat(),
    }
    return position, output_identifier, taxonomy_item, photo


def main() -> int:
    TAXONOMY_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    profiles, file_errors = load_profiles()
    seen: defaultdict[str, int] = defaultdict(int)
    work: list[tuple[int, str, dict]] = []
    for position, profile in enumerate(profiles, start=1):
        identifier = profile_id(profile)
        seen[identifier] += 1
        output_identifier = identifier if seen[identifier] == 1 else f"{identifier}--duplicate-{seen[identifier]}"
        work.append((position, output_identifier, profile))

    print(
        f"Audit parallèle de {len(profiles)} fiches avec {MAX_WORKERS} travailleurs.",
        flush=True,
    )
    completed: list[tuple[int, str, dict, dict]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="catalogue") as executor:
        futures = {
            executor.submit(audit_one, position, identifier, profile): (position, profile)
            for position, identifier, profile in work
        }
        for future in as_completed(futures):
            _position, profile = futures[future]
            result = future.result()
            completed.append(result)
            taxonomy_item = result[2]
            photo = result[3]
            print(
                f"[{len(completed)}/{len(profiles)}] {scientific_name(profile)} — "
                f"taxon={taxonomy_item['taxonomic'].get('status')} photo={photo.get('status')}",
                flush=True,
            )

    completed.sort(key=lambda item: item[0])
    taxonomy_output = {identifier: taxonomy for _, identifier, taxonomy, _ in completed}
    photos_output = {identifier: photo for _, identifier, _, photo in completed}
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    TAXONOMY_OUTPUT.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": generated_at,
                "profiles": taxonomy_output,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    PHOTOS_OUTPUT.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": generated_at,
                "license_policy": "Photos GBIF ou Wikimedia Commons avec licence ouverte et attribution conservée.",
                "profiles": photos_output,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    REPORT_OUTPUT.write_text(
        build_report(profiles, file_errors, taxonomy_output, photos_output),
        encoding="utf-8",
    )
    print(f"Rapport écrit dans {REPORT_OUTPUT}", flush=True)
    return 1 if file_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
