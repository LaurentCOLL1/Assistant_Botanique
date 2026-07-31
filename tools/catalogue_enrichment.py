"""Audit exhaustif du catalogue et recherche de photographies sous licence traçable.

Le script parcourt toutes les fiches de ``familles_plantes``. Il rapproche les
noms du référentiel taxonomique GBIF, contrôle les sections attendues et cherche
une photographie réutilisable, d'abord dans GBIF puis dans Wikimedia Commons.

Les résultats sont séparés des fiches historiques :
- catalogue_metadata/taxonomy_audit.json
- catalogue_metadata/photos.json
- catalogue_metadata/catalogue_audit_report.md
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FAMILIES_DIR = ROOT / "familles_plantes"
OUTPUT_DIR = ROOT / "catalogue_metadata"
TAXONOMY_OUTPUT = OUTPUT_DIR / "taxonomy_audit.json"
PHOTOS_OUTPUT = OUTPUT_DIR / "photos.json"
REPORT_OUTPUT = OUTPUT_DIR / "catalogue_audit_report.md"

GBIF_MATCH = "https://api.gbif.org/v1/species/match"
GBIF_SPECIES = "https://api.gbif.org/v1/species/{key}"
GBIF_MEDIA = "https://api.gbif.org/v1/species/{key}/media"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "AssistantBotaniqueCatalogueAudit/1.0 (https://github.com/LaurentCOLL1/Assistant_Botanique)"

MONTHS = (
    "janvier", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
)
REQUIRED_SECTIONS = (
    "taxonomie", "morphologie", "exigences_climatiques", "gestion_eau",
    "substrat", "entretien", "sante_securite",
)
OPEN_LICENSE_MARKERS = (
    "cc0", "public domain", "public_domain", "cc by", "cc-by", "cc_by",
    "pdm", "copyrighted free use",
)
DISALLOWED_LICENSE_MARKERS = ("-nc", " nc ", "noncommercial", "-nd", " no derivatives")
PHOTO_PENALTIES = (
    "distribution", "map", "range", "herbarium", "herbar", "specimen",
    "drawing", "illustration", "plate", "diagram", "icon", "logo", "seedling",
)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value)))
    return re.sub(r"\s+", " ", text).strip()


def normalize(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def scientific_name(profile: dict[str, Any]) -> str:
    tax = profile.get("taxonomie") if isinstance(profile.get("taxonomie"), dict) else {}
    return str(tax.get("nom_scientifique") or profile.get("nom_sci") or "Inconnu").strip()


def family_name(profile: dict[str, Any]) -> str:
    tax = profile.get("taxonomie") if isinstance(profile.get("taxonomie"), dict) else {}
    return str(tax.get("famille") or "Non renseignée").strip()


def profile_id(profile: dict[str, Any]) -> str:
    explicit = str(profile.get("id") or "").strip()
    return explicit or normalize(scientific_name(profile))


def request_json(url: str, *, params: dict[str, Any] | None = None, retries: int = 3) -> Any:
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code == 429 or 500 <= exc.code < 600:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt + 1 >= retries:
                raise
            time.sleep(1.5 * (attempt + 1))
    return None


def load_profiles() -> tuple[list[dict[str, Any]], list[str]]:
    profiles: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in sorted(FAMILIES_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: JSON illisible: {exc}")
            continue
        if not isinstance(payload, list):
            errors.append(f"{path.name}: la racine doit être une liste")
            continue
        for index, raw in enumerate(payload, start=1):
            if not isinstance(raw, dict):
                errors.append(f"{path.name}[{index}]: entrée non objet")
                continue
            item = dict(raw)
            item["_source_file"] = path.name
            item["_source_index"] = index
            profiles.append(item)
    return profiles, errors


def structural_audit(profile: dict[str, Any]) -> dict[str, Any]:
    missing_sections = [section for section in REQUIRED_SECTIONS if not isinstance(profile.get(section), dict)]
    missing_fields: list[str] = []
    tax = profile.get("taxonomie") if isinstance(profile.get("taxonomie"), dict) else {}
    for key in ("nom_scientifique", "noms_vernaculaires", "famille", "origine_geographique"):
        if tax.get(key) in (None, "", []):
            missing_fields.append(f"taxonomie.{key}")
    water = profile.get("gestion_eau") if isinstance(profile.get("gestion_eau"), dict) else {}
    frequency = water.get("frequence_arrosage") if isinstance(water.get("frequence_arrosage"), dict) else {}
    missing_months = [month for month in MONTHS if month not in frequency]
    invalid_months = {
        month: value
        for month, value in frequency.items()
        if month not in MONTHS or not isinstance(value, int) or value < 0
    }
    metadata = profile.get("metadata") if isinstance(profile.get("metadata"), dict) else {}
    sources = [str(value).strip() for value in metadata.get("sources", []) if str(value).strip()]
    return {
        "complete": not missing_sections and not missing_fields and not missing_months and not invalid_months,
        "missing_sections": missing_sections,
        "missing_fields": missing_fields,
        "missing_watering_months": missing_months,
        "invalid_watering_values": invalid_months,
        "has_sources": bool(sources),
        "source_count": len(sources),
    }


def genus_fallback(name: str) -> str:
    parts = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ×-]+", name)
    return parts[0] if parts else name


def taxonomic_match(profile: dict[str, Any]) -> dict[str, Any]:
    name = scientific_name(profile)
    family = family_name(profile)
    generic = bool(re.search(r"\b(?:spp?|hybrides?|cultivars?)\.?\b|[&,/]", name, re.IGNORECASE))
    query_name = genus_fallback(name) if generic else name
    params: dict[str, Any] = {"name": query_name, "kingdom": "Plantae", "verbose": "true"}
    if family and family != "Non renseignée":
        params["family"] = family
    try:
        payload = request_json(GBIF_MATCH, params=params)
    except Exception as exc:  # noqa: BLE001 - audit must continue for all profiles
        return {
            "status": "api_error",
            "query_name": query_name,
            "generic_profile": generic,
            "error": f"{type(exc).__name__}: {exc}",
        }
    if not isinstance(payload, dict) or not payload.get("usageKey"):
        return {
            "status": "unmatched",
            "query_name": query_name,
            "generic_profile": generic,
            "match_type": payload.get("matchType") if isinstance(payload, dict) else None,
            "confidence": payload.get("confidence") if isinstance(payload, dict) else None,
            "note": payload.get("note") if isinstance(payload, dict) else None,
        }
    matched_family = str(payload.get("family") or "")
    family_consistent = not family or family == "Non renseignée" or matched_family.casefold() == family.casefold()
    matched_status = str(payload.get("status") or "UNKNOWN")
    canonical = str(payload.get("canonicalName") or payload.get("scientificName") or "")
    accepted_key = payload.get("acceptedUsageKey") or payload.get("usageKey")
    match_type = str(payload.get("matchType") or "UNKNOWN")
    confidence = payload.get("confidence")
    if generic:
        status = "generic_match"
    elif not family_consistent:
        status = "family_mismatch"
    elif match_type == "EXACT" and matched_status == "ACCEPTED":
        status = "accepted_exact"
    elif matched_status in {"SYNONYM", "HETEROTYPIC_SYNONYM", "HOMOTYPIC_SYNONYM"}:
        status = "synonym"
    elif match_type in {"FUZZY", "HIGHERRANK"}:
        status = "approximate"
    else:
        status = "matched_review"
    return {
        "status": status,
        "query_name": query_name,
        "generic_profile": generic,
        "usage_key": payload.get("usageKey"),
        "accepted_usage_key": accepted_key,
        "match_type": match_type,
        "confidence": confidence,
        "taxonomic_status": matched_status,
        "canonical_name": canonical,
        "scientific_name": payload.get("scientificName"),
        "accepted_scientific_name": payload.get("acceptedScientificName"),
        "rank": payload.get("rank"),
        "kingdom": payload.get("kingdom"),
        "phylum": payload.get("phylum"),
        "class": payload.get("class"),
        "order": payload.get("order"),
        "family": matched_family,
        "genus": payload.get("genus"),
        "family_consistent": family_consistent,
        "issues": payload.get("issues") or [],
        "gbif_url": f"https://www.gbif.org/species/{accepted_key}",
        "powo_search_url": "https://powo.science.kew.org/results?" + urllib.parse.urlencode({"q": canonical or name}),
    }


def license_is_open(value: str) -> bool:
    normalized = f" {value.casefold()} "
    return any(marker in normalized for marker in OPEN_LICENSE_MARKERS) and not any(
        marker in normalized for marker in DISALLOWED_LICENSE_MARKERS
    )


def gbif_photo(taxon: dict[str, Any]) -> dict[str, Any] | None:
    key = taxon.get("accepted_usage_key") or taxon.get("usage_key")
    if not key:
        return None
    try:
        payload = request_json(GBIF_MEDIA.format(key=key))
    except Exception:
        return None
    media_items: list[dict[str, Any]] = []
    if isinstance(payload, list):
        media_items = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        values = payload.get("results") or payload.get("media") or []
        if isinstance(values, list):
            media_items = [item for item in values if isinstance(item, dict)]
    candidates: list[tuple[int, dict[str, Any]]] = []
    for item in media_items:
        image_url = str(item.get("identifier") or item.get("url") or "").strip()
        page_url = str(item.get("references") or "").strip()
        license_name = str(item.get("license") or item.get("rights") or "").strip()
        media_type = str(item.get("type") or "").casefold()
        if not image_url or (media_type and "still" not in media_type and "image" not in media_type):
            continue
        if not license_is_open(license_name):
            continue
        title = clean_text(item.get("title") or item.get("description") or "")
        score = 50
        lowered = f"{title} {image_url}".casefold()
        score -= sum(12 for token in PHOTO_PENALTIES if token in lowered)
        if page_url:
            score += 5
        candidates.append((score, {
            "status": "found",
            "source": "GBIF",
            "image_url": image_url,
            "thumbnail_url": image_url,
            "page_url": page_url or f"https://www.gbif.org/species/{key}",
            "title": title,
            "author": clean_text(item.get("creator") or item.get("rightsHolder") or ""),
            "license": license_name,
            "license_url": str(item.get("licenseUrl") or "").strip(),
            "attribution": clean_text(item.get("credit") or item.get("rightsHolder") or item.get("creator") or ""),
            "taxon_key": key,
        }))
    return max(candidates, key=lambda pair: pair[0])[1] if candidates else None


def commons_photo(name: str, *, representative: bool = False) -> dict[str, Any] | None:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f'filetype:bitmap "{name}"',
        "gsrnamespace": 6,
        "gsrlimit": 12,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 900,
        "format": "json",
        "formatversion": 2,
    }
    try:
        payload = request_json(COMMONS_API, params=params)
    except Exception:
        return None
    pages = payload.get("query", {}).get("pages", []) if isinstance(payload, dict) else []
    candidates: list[tuple[int, dict[str, Any]]] = []
    target = normalize(name)
    for page in pages if isinstance(pages, list) else []:
        if not isinstance(page, dict):
            continue
        info_list = page.get("imageinfo") or []
        if not info_list or not isinstance(info_list[0], dict):
            continue
        info = info_list[0]
        metadata = info.get("extmetadata") if isinstance(info.get("extmetadata"), dict) else {}
        license_name = clean_text((metadata.get("LicenseShortName") or {}).get("value"))
        usage_terms = clean_text((metadata.get("UsageTerms") or {}).get("value"))
        combined_license = " ".join(part for part in (license_name, usage_terms) if part)
        if not license_is_open(combined_license):
            continue
        title = str(page.get("title") or "")
        description = clean_text((metadata.get("ImageDescription") or {}).get("value"))
        lowered = f"{title} {description}".casefold()
        score = 60
        title_normalized = normalize(title.removeprefix("File:"))
        if target and target in title_normalized:
            score += 40
        elif all(part in title_normalized for part in target.split("-")[:2]):
            score += 20
        score -= sum(15 for token in PHOTO_PENALTIES if token in lowered)
        image_url = str(info.get("url") or "").strip()
        thumb_url = str(info.get("thumburl") or image_url).strip()
        if not image_url:
            continue
        page_url = "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe=":()_-.,")
        author = clean_text((metadata.get("Artist") or {}).get("value"))
        credit = clean_text((metadata.get("Credit") or {}).get("value"))
        attribution = clean_text((metadata.get("Attribution") or {}).get("value")) or credit or author
        license_url = clean_text((metadata.get("LicenseUrl") or {}).get("value"))
        candidates.append((score, {
            "status": "representative" if representative else "found",
            "source": "Wikimedia Commons",
            "image_url": image_url,
            "thumbnail_url": thumb_url,
            "page_url": page_url,
            "title": title.removeprefix("File:"),
            "description": description,
            "author": author,
            "license": combined_license,
            "license_url": license_url,
            "attribution": attribution,
        }))
    return max(candidates, key=lambda pair: pair[0])[1] if candidates else None


def find_photo(profile: dict[str, Any], taxon: dict[str, Any]) -> dict[str, Any]:
    name = scientific_name(profile)
    generic = bool(taxon.get("generic_profile"))
    result = gbif_photo(taxon)
    if result:
        result["representative"] = generic
    else:
        query = taxon.get("canonical_name") or taxon.get("query_name") or name
        result = commons_photo(str(query), representative=generic)
    if not result and not generic:
        genus = genus_fallback(name)
        if genus and genus != name:
            result = commons_photo(genus, representative=True)
    if not result:
        result = {
            "status": "not_found",
            "source": None,
            "image_url": None,
            "thumbnail_url": None,
            "page_url": None,
            "author": None,
            "license": None,
            "license_url": None,
            "attribution": None,
            "representative": generic,
        }
    result["scientific_name"] = name
    result["retrieved_at"] = date.today().isoformat()
    return result


def build_report(
    profiles: list[dict[str, Any]],
    file_errors: list[str],
    taxonomy: dict[str, dict[str, Any]],
    photos: dict[str, dict[str, Any]],
) -> str:
    family_counts = Counter(family_name(profile) for profile in profiles)
    tax_counts = Counter(item.get("taxonomic", {}).get("status", "unknown") for item in taxonomy.values())
    photo_counts = Counter(item.get("status", "unknown") for item in photos.values())
    incomplete = [item for item in taxonomy.values() if not item.get("structure", {}).get("complete")]
    mismatches = [item for item in taxonomy.values() if item.get("taxonomic", {}).get("status") == "family_mismatch"]
    approximate = [
        item for item in taxonomy.values()
        if item.get("taxonomic", {}).get("status") in {"approximate", "unmatched", "api_error", "matched_review"}
    ]
    synonyms = [item for item in taxonomy.values() if item.get("taxonomic", {}).get("status") == "synonym"]
    missing_photos = [item for item in photos.values() if item.get("status") == "not_found"]

    lines = [
        "# Audit exhaustif du catalogue botanique",
        "",
        f"Généré le {datetime.now(timezone.utc).isoformat(timespec='seconds')}.",
        "",
        "## Portée et limites",
        "",
        "Toutes les entrées JSON du dossier `familles_plantes` ont été parcourues. Le rapprochement taxonomique est effectué avec le référentiel GBIF. Les contrôles horticoles automatisés vérifient la présence et la cohérence formelle des rubriques, mais ne remplacent pas une revue humaine de chaque recommandation de culture.",
        "",
        "## Résumé",
        "",
        f"- Fichiers de familles : **{len(list(FAMILIES_DIR.glob('*.json')))}**",
        f"- Fiches parcourues : **{len(profiles)}**",
        f"- Familles représentées : **{len(family_counts)}**",
        f"- Fiches structurellement complètes : **{len(profiles) - len(incomplete)}**",
        f"- Photos exactes trouvées : **{photo_counts.get('found', 0)}**",
        f"- Photos représentatives de genre/groupe : **{photo_counts.get('representative', 0)}**",
        f"- Photos non trouvées : **{len(missing_photos)}**",
        "",
        "## Résultats taxonomiques",
        "",
    ]
    for status, count in sorted(tax_counts.items()):
        lines.append(f"- `{status}` : {count}")
    lines.extend(["", "## Répartition par famille", ""])
    for family, count in sorted(family_counts.items(), key=lambda pair: (-pair[1], pair[0].casefold())):
        lines.append(f"- {family} : {count}")

    def append_items(title: str, items: list[dict[str, Any]], formatter) -> None:
        lines.extend(["", f"## {title}", ""])
        if not items:
            lines.append("Aucune.")
            return
        for item in items:
            lines.append(f"- {formatter(item)}")

    append_items(
        "Noms synonymes à envisager de mettre à jour",
        synonyms,
        lambda item: f"**{item['scientific_name']}** → {item['taxonomic'].get('accepted_scientific_name') or item['taxonomic'].get('canonical_name')}",
    )
    append_items(
        "Incohérences de famille",
        mismatches,
        lambda item: f"**{item['scientific_name']}** : fiche `{item['declared_family']}`, GBIF `{item['taxonomic'].get('family')}`",
    )
    append_items(
        "Correspondances taxonomiques à revoir manuellement",
        approximate,
        lambda item: f"**{item['scientific_name']}** — `{item['taxonomic'].get('status')}` ({item['source_file']}[{item['source_index']}])",
    )
    append_items(
        "Fiches incomplètes",
        incomplete,
        lambda item: f"**{item['scientific_name']}** — sections: {', '.join(item['structure'].get('missing_sections') or ['aucune'])}; champs: {', '.join(item['structure'].get('missing_fields') or ['aucun'])}; mois: {', '.join(item['structure'].get('missing_watering_months') or ['aucun'])}",
    )
    append_items(
        "Photos restant à trouver",
        missing_photos,
        lambda item: f"**{item['scientific_name']}**",
    )
    if file_errors:
        lines.extend(["", "## Erreurs de fichiers", ""])
        lines.extend(f"- {error}" for error in file_errors)
    lines.extend([
        "",
        "## Sources techniques",
        "",
        "- GBIF Species API : https://techdocs.gbif.org/en/openapi/v1/species",
        "- Wikimedia Commons API : https://commons.wikimedia.org/wiki/Commons:API",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    profiles, file_errors = load_profiles()
    taxonomy_output: dict[str, dict[str, Any]] = {}
    photos_output: dict[str, dict[str, Any]] = {}
    seen: defaultdict[str, int] = defaultdict(int)

    print(f"Audit de {len(profiles)} fiches dans {len(list(FAMILIES_DIR.glob('*.json')))} fichiers.", flush=True)
    for position, profile in enumerate(profiles, start=1):
        identifier = profile_id(profile)
        seen[identifier] += 1
        output_identifier = identifier if seen[identifier] == 1 else f"{identifier}--duplicate-{seen[identifier]}"
        taxon = taxonomic_match(profile)
        structure = structural_audit(profile)
        photo = find_photo(profile, taxon)
        taxonomy_output[output_identifier] = {
            "scientific_name": scientific_name(profile),
            "declared_family": family_name(profile),
            "source_file": profile.get("_source_file"),
            "source_index": profile.get("_source_index"),
            "structure": structure,
            "taxonomic": taxon,
            "reviewed_at": date.today().isoformat(),
        }
        photos_output[output_identifier] = photo
        print(
            f"[{position}/{len(profiles)}] {scientific_name(profile)} — "
            f"taxon={taxon.get('status')} photo={photo.get('status')}",
            flush=True,
        )
        time.sleep(0.08)

    taxonomy_payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "profiles": taxonomy_output,
    }
    photos_payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "license_policy": "Photos GBIF ou Wikimedia Commons avec licence ouverte et attribution conservée.",
        "profiles": photos_output,
    }
    TAXONOMY_OUTPUT.write_text(json.dumps(taxonomy_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PHOTOS_OUTPUT.write_text(json.dumps(photos_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_OUTPUT.write_text(
        build_report(profiles, file_errors, taxonomy_output, photos_output),
        encoding="utf-8",
    )
    print(f"Rapport écrit dans {REPORT_OUTPUT.relative_to(ROOT)}", flush=True)
    return 1 if file_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
