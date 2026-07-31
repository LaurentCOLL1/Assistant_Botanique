"""Complète les photos manquantes avec les occurrences illustrées de GBIF."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from catalogue_enrichment import (
    PHOTOS_OUTPUT,
    REPORT_OUTPUT,
    TAXONOMY_OUTPUT,
    USER_AGENT,
    build_report,
    clean_text,
    load_profiles,
)

OCCURRENCE_API = "https://api.gbif.org/v1/occurrence/search"
MAX_WORKERS = 20
REQUEST_TIMEOUT = 8
PENALTIES = (
    "herbarium", "herbar", "specimen", "sheet", "label", "barcode",
    "drawing", "illustration", "plate", "map", "distribution",
)


def open_license(value: str) -> bool:
    normalized = value.casefold().replace("_", "-")
    if any(marker in normalized for marker in ("by-nc", "by-nd", "noncommercial", "no derivatives")):
        return False
    return any(
        marker in normalized
        for marker in (
            "cc0", "public domain", "publicdomain", "creativecommons.org/publicdomain",
            "creativecommons.org/licenses/by/", "creativecommons.org/licenses/by-sa/",
            "cc by ", "cc-by-", "cc by-sa", "cc-by-sa",
        )
    )


def request_occurrences(taxon_key: int) -> dict[str, Any] | None:
    params = urllib.parse.urlencode(
        {
            "taxon_key": taxon_key,
            "media_type": "StillImage",
            "limit": 20,
        }
    )
    request = urllib.request.Request(
        f"{OCCURRENCE_API}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if (exc.code == 429 or 500 <= exc.code < 600) and attempt == 0:
                time.sleep(1.0)
                continue
            return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == 0:
                time.sleep(0.5)
                continue
            return None
    return None


def photo_from_occurrence(taxon_key: int, scientific_name: str) -> dict[str, Any] | None:
    payload = request_occurrences(taxon_key)
    results = payload.get("results", []) if isinstance(payload, dict) else []
    candidates: list[tuple[int, dict[str, Any]]] = []
    for occurrence in results if isinstance(results, list) else []:
        if not isinstance(occurrence, dict):
            continue
        basis = str(occurrence.get("basisOfRecord") or "").casefold()
        occurrence_page = (
            str(occurrence.get("references") or "").strip()
            or f"https://www.gbif.org/occurrence/{occurrence.get('key')}"
        )
        for media in occurrence.get("media", []) if isinstance(occurrence.get("media"), list) else []:
            if not isinstance(media, dict):
                continue
            image_url = str(media.get("identifier") or "").strip()
            license_name = str(media.get("license") or media.get("rights") or "").strip()
            if not image_url or not open_license(license_name):
                continue
            media_type = str(media.get("type") or "").casefold()
            if media_type and "still" not in media_type and "image" not in media_type:
                continue
            title = clean_text(media.get("title") or media.get("description") or "")
            lowered = f"{title} {image_url}".casefold()
            score = 100
            if "preserved" in basis or "specimen" in basis:
                score -= 35
            score -= sum(20 for marker in PENALTIES if marker in lowered)
            if occurrence.get("issues"):
                score -= 5
            author = clean_text(
                media.get("creator")
                or media.get("rightsHolder")
                or occurrence.get("recordedBy")
                or ""
            )
            attribution = clean_text(
                media.get("credit")
                or media.get("rightsHolder")
                or media.get("creator")
                or occurrence.get("institutionCode")
                or ""
            )
            candidates.append(
                (
                    score,
                    {
                        "status": "found",
                        "source": "GBIF occurrence",
                        "image_url": image_url,
                        "thumbnail_url": image_url,
                        "page_url": occurrence_page,
                        "title": title,
                        "description": clean_text(media.get("description") or ""),
                        "author": author,
                        "license": license_name,
                        "license_url": license_name if license_name.startswith("http") else "",
                        "attribution": attribution,
                        "scientific_name": scientific_name,
                        "taxon_key": taxon_key,
                        "occurrence_key": occurrence.get("key"),
                        "retrieved_at": datetime.now(timezone.utc).date().isoformat(),
                    },
                )
            )
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def main() -> int:
    taxonomy_payload = json.loads(TAXONOMY_OUTPUT.read_text(encoding="utf-8"))
    photos_payload = json.loads(PHOTOS_OUTPUT.read_text(encoding="utf-8"))
    taxonomy = taxonomy_payload.get("profiles", {})
    photos = photos_payload.get("profiles", {})
    jobs: list[tuple[str, int, str]] = []
    for identifier, photo in photos.items():
        if photo.get("status") != "not_found":
            continue
        audit = taxonomy.get(identifier, {})
        taxonomic = audit.get("taxonomic") if isinstance(audit.get("taxonomic"), dict) else {}
        key = taxonomic.get("accepted_usage_key") or taxonomic.get("usage_key")
        if isinstance(key, int):
            jobs.append((identifier, key, str(audit.get("scientific_name") or identifier)))

    added = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="gbif-photo") as executor:
        futures = {
            executor.submit(photo_from_occurrence, key, name): (identifier, name)
            for identifier, key, name in jobs
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            identifier, _name = futures[future]
            candidate = future.result()
            if candidate:
                photos[identifier] = candidate
                added += 1
            if completed % 50 == 0 or completed == len(futures):
                print(f"GBIF: {completed}/{len(futures)}, {added} photo(s) ajoutée(s).", flush=True)

    photos_payload["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    photos_payload["license_policy"] = (
        "Photographies Wikimedia Commons ou occurrences GBIF avec licence ouverte, auteur et page source."
    )
    photos_payload["profiles"] = photos
    photos_payload["sources"] = dict(Counter(photo.get("source") or "aucune" for photo in photos.values()))
    PHOTOS_OUTPUT.write_text(
        json.dumps(photos_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    profiles, file_errors = load_profiles()
    REPORT_OUTPUT.write_text(
        build_report(profiles, file_errors, taxonomy, photos),
        encoding="utf-8",
    )
    print(f"Passage GBIF terminé: {added} photo(s) ajoutée(s).", flush=True)
    return 1 if file_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
