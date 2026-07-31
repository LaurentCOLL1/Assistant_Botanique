"""Complète en lots les photographies manquantes à partir de Wikipédia/Commons."""
from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from catalogue_enrichment import (
    PHOTOS_OUTPUT,
    REPORT_OUTPUT,
    TAXONOMY_OUTPUT,
    USER_AGENT,
    build_report,
    clean_text,
    license_is_open,
    load_profiles,
)

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
BATCH_SIZE = 40
REQUEST_TIMEOUT = 15
REQUEST_RETRIES = 3
PENALTIES = (
    "distribution", "range map", "map", "herbarium", "herbar", "specimen",
    "drawing", "illustration", "plate", "diagram", "icon", "logo",
)


def chunks(values: list[Any], size: int = BATCH_SIZE) -> Iterable[list[Any]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def request_json(url: str, params: dict[str, Any]) -> Any:
    target = url + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        target,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    for attempt in range(REQUEST_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code == 429 or 500 <= exc.code < 600:
                if attempt + 1 < REQUEST_RETRIES:
                    time.sleep(1.5 * (attempt + 1))
                    continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt + 1 >= REQUEST_RETRIES:
                raise
            time.sleep(1.5 * (attempt + 1))
    return None


def base_query_name(scientific_name: str, taxonomic: dict[str, Any]) -> tuple[str, bool]:
    accepted = str(
        taxonomic.get("accepted_scientific_name")
        or taxonomic.get("canonical_name")
        or scientific_name
    ).strip()
    accepted = re.sub(r"\s+[A-Z][A-Za-z.-]*(?:\s+ex\s+[A-Z][A-Za-z.-]*)?$", "", accepted).strip()
    representative = bool(taxonomic.get("generic_profile"))
    if re.search(r"\b(?:spp?|hybrides?|cultivars?)\.?\b", accepted, re.IGNORECASE):
        accepted = accepted.split()[0]
        representative = True
    if "'" in accepted or '"' in accepted:
        quoted = re.sub(r"\s+['\"].*$", "", accepted).strip()
        if quoted:
            accepted = quoted
            representative = True
    words = accepted.split()
    if len(words) > 3 and words[2].casefold() not in {"subsp.", "var.", "f."}:
        accepted = " ".join(words[:2])
        representative = True
    return accepted or scientific_name, representative


def resolve_alias(title: str, aliases: dict[str, str]) -> str:
    seen: set[str] = set()
    current = title
    while current in aliases and current not in seen:
        seen.add(current)
        current = aliases[current]
    return current


def wikipedia_page_images(queries: list[str]) -> dict[str, dict[str, Any]]:
    payload = request_json(
        WIKIPEDIA_API,
        {
            "action": "query",
            "titles": "|".join(queries),
            "redirects": "1",
            "prop": "pageimages",
            "piprop": "name|thumbnail|original",
            "pithumbsize": "960",
            "format": "json",
            "formatversion": "2",
        },
    )
    query = payload.get("query", {}) if isinstance(payload, dict) else {}
    aliases: dict[str, str] = {}
    for key in ("normalized", "redirects"):
        for item in query.get(key, []) if isinstance(query.get(key), list) else []:
            if isinstance(item, dict) and item.get("from") and item.get("to"):
                aliases[str(item["from"])] = str(item["to"])
    pages = {
        str(page.get("title")): page
        for page in query.get("pages", []) if isinstance(query.get("pages"), list)
        if isinstance(page, dict) and not page.get("missing")
    }
    result: dict[str, dict[str, Any]] = {}
    for original in queries:
        resolved = resolve_alias(original, aliases)
        page = pages.get(resolved)
        if page and page.get("pageimage"):
            result[original] = page
    return result


def normalize_file_title(value: str) -> str:
    value = value.removeprefix("File:").replace("_", " ")
    return html.unescape(value).strip().casefold()


def commons_metadata(filenames: list[str]) -> dict[str, dict[str, Any]]:
    payload = request_json(
        COMMONS_API,
        {
            "action": "query",
            "titles": "|".join(f"File:{name}" for name in filenames),
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": "960",
            "format": "json",
            "formatversion": "2",
        },
    )
    pages = payload.get("query", {}).get("pages", []) if isinstance(payload, dict) else []
    result: dict[str, dict[str, Any]] = {}
    for page in pages if isinstance(pages, list) else []:
        if not isinstance(page, dict) or page.get("missing"):
            continue
        info_list = page.get("imageinfo") or []
        if not info_list or not isinstance(info_list[0], dict):
            continue
        info = info_list[0]
        metadata = info.get("extmetadata") if isinstance(info.get("extmetadata"), dict) else {}
        license_name = clean_text((metadata.get("LicenseShortName") or {}).get("value"))
        usage_terms = clean_text((metadata.get("UsageTerms") or {}).get("value"))
        combined_license = " ".join(value for value in (license_name, usage_terms) if value)
        if not license_is_open(combined_license):
            continue
        title = str(page.get("title") or "")
        description = clean_text((metadata.get("ImageDescription") or {}).get("value"))
        lowered = f"{title} {description}".casefold()
        if any(token in lowered for token in PENALTIES):
            continue
        image_url = str(info.get("url") or "").strip()
        if not image_url:
            continue
        thumb_url = str(info.get("thumburl") or image_url).strip()
        page_url = "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(
            title.replace(" ", "_"), safe=":()_-.,"
        )
        author = clean_text((metadata.get("Artist") or {}).get("value"))
        credit = clean_text((metadata.get("Credit") or {}).get("value"))
        attribution = clean_text((metadata.get("Attribution") or {}).get("value")) or credit or author
        result[normalize_file_title(title)] = {
            "source": "Wikimedia Commons",
            "image_url": image_url,
            "thumbnail_url": thumb_url,
            "page_url": page_url,
            "title": title.removeprefix("File:"),
            "description": description,
            "author": author,
            "license": combined_license,
            "license_url": clean_text((metadata.get("LicenseUrl") or {}).get("value")),
            "attribution": attribution,
        }
    return result


def main() -> int:
    taxonomy_payload = json.loads(TAXONOMY_OUTPUT.read_text(encoding="utf-8"))
    photos_payload = json.loads(PHOTOS_OUTPUT.read_text(encoding="utf-8"))
    taxonomy = taxonomy_payload.get("profiles", {})
    photos = photos_payload.get("profiles", {})
    missing_ids = [identifier for identifier, photo in photos.items() if photo.get("status") == "not_found"]
    requests: list[dict[str, Any]] = []
    for identifier in missing_ids:
        audit = taxonomy.get(identifier, {})
        scientific_name = str(audit.get("scientific_name") or photos[identifier].get("scientific_name") or identifier)
        taxonomic = audit.get("taxonomic") if isinstance(audit.get("taxonomic"), dict) else {}
        query_name, representative = base_query_name(scientific_name, taxonomic)
        requests.append(
            {
                "id": identifier,
                "scientific_name": scientific_name,
                "query": query_name,
                "representative": representative or query_name.casefold() != scientific_name.casefold(),
            }
        )

    added = 0
    for batch_number, batch in enumerate(chunks(requests), start=1):
        query_names = list(dict.fromkeys(item["query"] for item in batch))
        try:
            pages = wikipedia_page_images(query_names)
        except Exception as exc:  # noqa: BLE001 - continue the exhaustive pass
            print(f"Lot {batch_number}: Wikipédia indisponible: {exc}", flush=True)
            continue
        filenames = list(dict.fromkeys(str(page["pageimage"]) for page in pages.values()))
        if not filenames:
            continue
        try:
            metadata_by_file = commons_metadata(filenames)
        except Exception as exc:  # noqa: BLE001
            print(f"Lot {batch_number}: Commons indisponible: {exc}", flush=True)
            continue
        for item in batch:
            page = pages.get(item["query"])
            if not page:
                continue
            filename = str(page.get("pageimage") or "")
            metadata = metadata_by_file.get(normalize_file_title(filename))
            if not metadata:
                continue
            photos[item["id"]] = {
                "status": "representative" if item["representative"] else "found",
                **metadata,
                "scientific_name": item["scientific_name"],
                "wikipedia_page": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(str(page.get('title')).replace(' ', '_'))}",
                "retrieved_at": datetime.now(timezone.utc).date().isoformat(),
            }
            added += 1
        print(
            f"Lot {batch_number}: {added} photo(s) ajoutée(s), "
            f"{min(batch_number * BATCH_SIZE, len(requests))}/{len(requests)} fiches examinées.",
            flush=True,
        )
        time.sleep(0.25)

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    photos_payload["generated_at"] = generated_at
    photos_payload["license_policy"] = (
        "Photographies de Wikimedia Commons sélectionnées via Wikipédia, avec auteur, licence et page source."
    )
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
    print(f"Second passage terminé: {added} photo(s) ajoutée(s).", flush=True)
    return 1 if file_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
