"""Dernier passage ciblé sur Wikimedia Commons pour les photos manquantes."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import catalogue_enrichment as base
from catalogue_enrichment import (
    PHOTOS_OUTPUT,
    REPORT_OUTPUT,
    TAXONOMY_OUTPUT,
    USER_AGENT,
    build_report,
    commons_photo,
    load_profiles,
)
from photo_batch_enrichment import base_query_name

MAX_WORKERS = 4
REQUEST_TIMEOUT = 15
REQUEST_RETRIES = 4


def patient_request_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    retries: int = REQUEST_RETRIES,
) -> Any:
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
            if exc.code == 429 or 500 <= exc.code < 600:
                if attempt + 1 < attempts:
                    time.sleep(2.0 * (attempt + 1))
                    continue
            return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt + 1 >= attempts:
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


base.request_json = patient_request_json


def find_one(identifier: str, scientific: str, taxonomic: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    query_name, representative = base_query_name(scientific, taxonomic)
    photo = commons_photo(query_name, representative=representative or query_name.casefold() != scientific.casefold())
    if photo:
        photo["scientific_name"] = scientific
        photo["retrieved_at"] = datetime.now(timezone.utc).date().isoformat()
    return identifier, photo


def main() -> int:
    taxonomy_payload = json.loads(TAXONOMY_OUTPUT.read_text(encoding="utf-8"))
    photos_payload = json.loads(PHOTOS_OUTPUT.read_text(encoding="utf-8"))
    taxonomy = taxonomy_payload.get("profiles", {})
    photos = photos_payload.get("profiles", {})
    jobs: list[tuple[str, str, dict[str, Any]]] = []
    for identifier, photo in photos.items():
        if photo.get("status") != "not_found":
            continue
        audit = taxonomy.get(identifier, {})
        taxonomic = audit.get("taxonomic") if isinstance(audit.get("taxonomic"), dict) else {}
        scientific = str(audit.get("scientific_name") or photo.get("scientific_name") or identifier)
        jobs.append((identifier, scientific, taxonomic))

    added = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="commons-target") as executor:
        futures = {
            executor.submit(find_one, identifier, scientific, taxonomic): scientific
            for identifier, scientific, taxonomic in jobs
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            identifier, candidate = future.result()
            if candidate:
                photos[identifier] = candidate
                added += 1
            if completed % 10 == 0 or completed == len(futures):
                print(
                    f"Commons ciblé: {completed}/{len(futures)}, {added} photo(s) ajoutée(s).",
                    flush=True,
                )

    photos_payload["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    photos_payload["profiles"] = photos
    PHOTOS_OUTPUT.write_text(
        json.dumps(photos_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    profiles, file_errors = load_profiles()
    REPORT_OUTPUT.write_text(
        build_report(profiles, file_errors, taxonomy, photos),
        encoding="utf-8",
    )
    print(f"Passage Commons ciblé terminé: {added} photo(s) ajoutée(s).", flush=True)
    return 1 if file_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
