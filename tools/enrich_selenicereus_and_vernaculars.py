"""Enrichit le catalogue en Selenicereus/pitayas et noms vernaculaires.

Principes :
- les 33 espèces acceptées de Selenicereus suivent Kew/POWO 2026 ;
- les cultivars de pitaya proviennent de sources institutionnelles ou d'une
  synthèse scientifique évaluée par les pairs ;
- pour les fiches historiques sans nom vernaculaire, aucun nom n'est inventé :
  seules les appellations explicitement renvoyées par GBIF ou iNaturalist sont
  ajoutées, avec leur provenance dans un rapport d'audit.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FAMILIES_DIR = ROOT / "familles_plantes"
OUTPUT_FILE = FAMILIES_DIR / "cactaceae_selenicereus.json"
REPORT_FILE = ROOT / "catalogue_metadata" / "vernacular_name_audit.json"

USER_AGENT = "AssistantBotaniqueVernacularAudit/1.1 (https://github.com/LaurentCOLL1/Assistant_Botanique)"
GBIF_MATCH = "https://api.gbif.org/v1/species/match"
GBIF_VERNACULAR = "https://api.gbif.org/v1/species/{key}/vernacularNames"
INAT_TAXA = "https://api.inaturalist.org/v1/taxa"

POWO_GENUS = "https://powo.science.kew.org/taxon/urn:lsid:ipni.org:names:30011812-2"
USDA_DRAGON_FRUIT = "https://content.govdelivery.com/accounts/USDAAPHIS/bulletins/31b6635"
UCANR_SCI_NAMES = "https://ucanr.edu/site/san-diego-county-small-farms/pitahaya-scientific-names"
USDA_ARS_TRIAL = "https://www.ars.usda.gov/research/publications/publication/?seqNo115=326654"
EMBRAPA_PITAYA = "https://www.infoteca.cnptia.embrapa.br/infoteca/handle/doc/1153838"
PITAYA_REVIEW = "https://doi.org/10.3390/plants12183212"

ACCEPTED_SELENICEREUS = (
    "Selenicereus alliodorus",
    "Selenicereus anthonyanus",
    "Selenicereus atropilosus",
    "Selenicereus calcaratus",
    "Selenicereus costaricensis",
    "Selenicereus dorschianus",
    "Selenicereus escuintlensis",
    "Selenicereus extensus",
    "Selenicereus glaber",
    "Selenicereus grandiflorus",
    "Selenicereus guatemalensis",
    "Selenicereus haberi",
    "Selenicereus hamatus",
    "Selenicereus inermis",
    "Selenicereus megalanthus",
    "Selenicereus minutiflorus",
    "Selenicereus monacanthus",
    "Selenicereus murrillii",
    "Selenicereus nelsonii",
    "Selenicereus ocamponis",
    "Selenicereus plumieri",
    "Selenicereus pteranthus",
    "Selenicereus purpusii",
    "Selenicereus setaceus",
    "Selenicereus spinulosus",
    "Selenicereus stenopterus",
    "Selenicereus tonduzii",
    "Selenicereus triangularis",
    "Selenicereus tricae",
    "Selenicereus undatus",
    "Selenicereus vagans",
    "Selenicereus validus",
    "Selenicereus wercklei",
)

COMMERCIAL_PITAYA_SPECIES = {
    "Selenicereus costaricensis",
    "Selenicereus guatemalensis",
    "Selenicereus megalanthus",
    "Selenicereus monacanthus",
    "Selenicereus ocamponis",
    "Selenicereus undatus",
}

# UC ANR publie ces 19 sélections sous l'ancienne combinaison Hylocereus.
# H. polyrhizus est converti en S. monacanthus conformément à POWO.
UCANR_CULTIVARS = (
    ("Cebra", "Selenicereus monacanthus"),
    ("Rosa", "Selenicereus monacanthus"),
    ("Orejona", "Selenicereus monacanthus"),
    ("Lisa", "Selenicereus monacanthus"),
    ("Sin Espinas", "Selenicereus sp."),
    ("San Ignacio", "Selenicereus monacanthus"),
    ("Mexicana", "Selenicereus undatus"),
    ("Columbiana", "Selenicereus megalanthus"),
    ("Valdivia Roja", "Selenicereus ocamponis"),
    ("Bien Hoa Red", "Selenicereus guatemalensis"),
    ("Bien Hoa White", "Selenicereus undatus"),
    ("Delight", "Selenicereus sp."),
    ("American Beauty", "Selenicereus guatemalensis"),
    ("Halley's Comet", "Selenicereus sp."),
    ("Physical Graffiti", "Selenicereus sp."),
    ("Vietnamese Giant", "Selenicereus undatus"),
    ("Seoul Kitchen", "Selenicereus undatus"),
    ("Armando", "Selenicereus monacanthus × Selenicereus costaricensis"),
    ("El Grullo", "Selenicereus ocamponis"),
)

# Noms explicitement présents dans l'étude USDA-ARS menée à Isabela, Porto Rico.
USDA_ARS_CULTIVARS = (
    "NOI-13",
    "NOI-14",
    "NOI-16",
    "N97-15",
    "N97-17",
    "N97-18",
    "N97-20",
    "N97-22",
    "Cosmic Charlie",
)

EMBRAPA_CULTIVARS = (
    ("BRS Lua do Cerrado", "Selenicereus undatus"),
    ("BRS Luz do Cerrado", "Selenicereus undatus"),
    ("BRS Âmbar do Cerrado", "Selenicereus megalanthus"),
    ("BRS Minipitaya do Cerrado", "Selenicereus setaceus"),
    ("BRS Granada do Cerrado", "Selenicereus undatus × Selenicereus costaricensis"),
)

# Cultivars supplémentaires documentés par la revue Plants 2023 consacrée à la
# culture de la pitaya dans la péninsule Ibérique. Les doublons sont éliminés.
LITERATURE_CULTIVARS = (
    ("Common White", "Selenicereus undatus"),
    ("Vietnamese White", "Selenicereus undatus"),
    ("Golden", "Selenicereus undatus"),
    ("Golden of Israel", "Selenicereus undatus"),
    ("Golden Isis", "Selenicereus undatus"),
    ("Tesoro", "Selenicereus monacanthus"),
    ("Costa Rica", "Selenicereus costaricensis"),
    ("Palora", "Selenicereus megalanthus"),
    ("Colombian yellow", "Selenicereus megalanthus"),
    ("Churuja", "Selenicereus megalanthus"),
    ("Golden Ball", "Selenicereus megalanthus"),
    ("Boliviana", "Selenicereus megalanthus"),
    ("Amazonas", "Selenicereus megalanthus"),
    ("Hybridum", "Selenicereus monacanthus × Selenicereus undatus"),
    ("Boreal Red", "Selenicereus sp."),
    ("Taiwan Red", "Selenicereus sp."),
    ("DF 14", "Selenicereus sp."),
    ("DF 16", "Selenicereus sp."),
    ("Purple Haze", "Selenicereus sp."),
)


def request_json(url: str, params: dict[str, Any] | None = None, retries: int = 3) -> Any:
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code == 429 or 500 <= exc.code < 600:
                time.sleep(1.0 + attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt + 1 >= retries:
                return None
            time.sleep(1.0 + attempt)
    return None


def slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    value = value.replace("×", " x ")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def taxonomy(profile: dict[str, Any]) -> dict[str, Any]:
    value = profile.get("taxonomie")
    return value if isinstance(value, dict) else {}


def scientific_name(profile: dict[str, Any]) -> str:
    return str(taxonomy(profile).get("nom_scientifique") or "").strip()


def vernacular_names(profile: dict[str, Any]) -> list[str]:
    names = taxonomy(profile).get("noms_vernaculaires")
    if not isinstance(names, list):
        return []
    return [str(value).strip() for value in names if str(value).strip()]


def load_family_files() -> list[tuple[Path, list[dict[str, Any]]]]:
    result: list[tuple[Path, list[dict[str, Any]]]] = []
    for path in sorted(FAMILIES_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, list):
            result.append((path, [item for item in payload if isinstance(item, dict)]))
    return result


def base_profile(name: str, *, cultivar: str | None = None, source: str = POWO_GENUS) -> dict[str, Any]:
    fruiting = name in COMMERCIAL_PITAYA_SPECIES or cultivar is not None
    display_scientific = f"{name} '{cultivar}'" if cultivar else name
    sources = [POWO_GENUS, source]
    if fruiting:
        sources.append(USDA_DRAGON_FRUIT)
    return {
        "id": slug(display_scientific),
        "taxonomie": {
            "nom_scientifique": display_scientific,
            # Un cultivar a un nom horticole attesté ; pour une espèce, les noms
            # communs seront recherchés plus bas dans GBIF/iNaturalist.
            "noms_vernaculaires": [cultivar] if cultivar else [],
            "famille": "Cactaceae",
            "origine_geographique": "Mexique à Amérique tropicale ; aire exacte variable selon le taxon",
        },
        "morphologie": {
            "port": "Cactus grimpant ou retombant, épiphyte à hémiépiphyte, à longues tiges côtelées",
            "systeme_racinaire": "Racines terrestres et racines aériennes d'ancrage",
            "feuillage": {
                "persistance": "Feuilles absentes ; tiges chlorophylliennes persistantes",
                "morphologie": "Tiges succulentes côtelées ou ailées, plus ou moins épineuses selon l'espèce",
                "coloris_motifs": "Vert à vert bleuté",
            },
            "fleurs": {
                "description": "Grandes fleurs généralement nocturnes, blanches à crème, parfois teintées de jaune ou de rose",
                "parfum": "Souvent parfumé la nuit",
            },
            "floraison": "Principalement de la fin du printemps à l'été, selon le climat",
            "fruits_graines": (
                "Baies charnues comestibles de type pitaya, couleur et chair variables selon le cultivar"
                if fruiting else "Baies charnues ; intérêt fruitier variable selon l'espèce"
            ),
        },
        "exigences_climatiques": {
            "temperature_ideale": "18°C à 30°C",
            "rusticite": "Craint le gel prolongé ; culture hors gel recommandée",
            "exposition": "Lumière vive à soleil filtré ; soleil direct progressif en culture fruitière",
            "hygrometrie": "Moyenne à élevée avec bonne circulation d'air",
        },
        "gestion_eau": {
            "frequence_mode": "Arroser en croissance puis laisser la couche superficielle sécher ; réduire en hiver",
            "frequence_arrosage": {
                "janvier": 12, "fevrier": 12, "mars": 9, "avril": 7,
                "mai": 6, "juin": 5, "juillet": 5, "aout": 5,
                "septembre": 6, "octobre": 8, "novembre": 10, "decembre": 12,
            },
            "variation_saisonniere": "Plus d'eau en croissance et fructification ; nettement moins en période fraîche",
            "qualite_eau": "Eau peu calcaire de préférence",
            "sensibilite_minerale": "Sensible à l'asphyxie racinaire et à l'eau stagnante",
        },
        "substrat": {
            "ph": "5.5 - 7.0",
            "categorie_horticole": "Cactus épiphyte / pitaya",
            "modele_recherche": "succulent_mineral",
            "version_recherche": "2026.08-selenicereus",
            "roles": [
                {"nom": "Base organique", "ratio": 0.45, "ing": ["Terreau horticole", "Terreau léger"]},
                {"nom": "Structure", "ratio": 0.25, "ing": ["Écorces de pin"]},
                {"nom": "Aération", "ratio": 0.20, "ing": ["Perlite"]},
                {"nom": "Drainage", "ratio": 0.10, "ing": ["Pumice"]},
            ],
            "interdits": ["Terreau argileux (Aquatique / Nénuphars)"],
            "sources": [
                {"titre": "Kew POWO — Selenicereus", "url": POWO_GENUS},
                {"titre": "USDA APHIS — Dragon fruit", "url": USDA_DRAGON_FRUIT},
            ],
        },
        "entretien": {
            "rempotage": "Tous les 2 à 3 ans ou lorsque le système racinaire devient trop à l'étroit",
            "taille": "Tailler les tiges âgées ou encombrantes et palisser les pousses vigoureuses",
            "fertilisation": "Engrais équilibré modéré en croissance ; éviter les excès d'azote avant floraison",
            "multiplication": "Boutures de tiges ; semis pour la diversité génétique",
        },
        "sante_securite": {
            "ravageurs": ["Cochenilles", "Cochenilles farineuses", "Acariens"],
            "maladies": ["Pourriture racinaire", "Anthracnose", "Taches et chancres des tiges"],
            "toxicite": "Non toxique ; fruits des pitayas cultivés comestibles",
            "proprietes_particulieres": (
                "Cultivar de pitaya documenté par une source horticole ou scientifique"
                if cultivar else "Espèce du genre Selenicereus ; Hylocereus est traité comme synonyme par POWO"
            ),
        },
        "metadata": {
            "schema_version": 1,
            "sources": list(dict.fromkeys(sources)),
            "last_reviewed": date.today().isoformat(),
            "confidence": "elevee" if cultivar or name in COMMERCIAL_PITAYA_SPECIES else "moyenne",
            "review_status": "valide",
        },
    }


def generate_selenicereus(existing_names: set[str]) -> list[dict[str, Any]]:
    generated = [base_profile(name) for name in ACCEPTED_SELENICEREUS if name not in existing_names]
    seen: set[str] = set()

    def add_cultivars(values: tuple[tuple[str, str], ...], source: str) -> None:
        for cultivar, parent in values:
            marker = cultivar.casefold()
            if marker in seen:
                continue
            seen.add(marker)
            generated.append(base_profile(parent, cultivar=cultivar, source=source))

    add_cultivars(UCANR_CULTIVARS, UCANR_SCI_NAMES)
    add_cultivars(tuple((name, "Selenicereus sp.") for name in USDA_ARS_CULTIVARS), USDA_ARS_TRIAL)
    add_cultivars(EMBRAPA_CULTIVARS, EMBRAPA_PITAYA)
    add_cultivars(LITERATURE_CULTIVARS, PITAYA_REVIEW)
    return generated


def clean_candidate(value: Any, scientific: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" ,;\t\n")
    if not text or len(text) < 2 or len(text) > 100:
        return ""
    lowered = text.casefold()
    if lowered == scientific.casefold() or "http://" in lowered or "https://" in lowered:
        return ""
    return text


def gbif_names(scientific: str, family: str) -> tuple[list[dict[str, str]], str | None]:
    params = {"name": scientific, "kingdom": "Plantae"}
    if family:
        params["family"] = family
    match = request_json(GBIF_MATCH, params)
    if not isinstance(match, dict) or not match.get("usageKey"):
        return [], None
    key = match.get("acceptedUsageKey") or match.get("usageKey")
    payload = request_json(GBIF_VERNACULAR.format(key=key), {"limit": 1000})
    rows = payload if isinstance(payload, list) else (payload or {}).get("results", []) if isinstance(payload, dict) else []
    candidates: list[dict[str, str]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        value = clean_candidate(row.get("vernacularName"), scientific)
        if not value:
            continue
        candidates.append({
            "name": value,
            "language": str(row.get("language") or "").casefold(),
            "provider": "GBIF",
            "source": str(row.get("source") or "GBIF").strip(),
            "url": f"https://www.gbif.org/species/{key}",
        })
    return candidates, str(key)


def inat_names(scientific: str) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for locale in ("fr", "en", "es", "pt"):
        payload = request_json(INAT_TAXA, {"q": scientific, "rank": "species", "locale": locale, "per_page": 10})
        results = payload.get("results", []) if isinstance(payload, dict) else []
        for row in results if isinstance(results, list) else []:
            if not isinstance(row, dict):
                continue
            row_name = str(row.get("name") or "").strip()
            matched = str(row.get("matched_term") or "").strip()
            if row_name.casefold() != scientific.casefold() and matched.casefold() != scientific.casefold():
                continue
            value = clean_candidate(row.get("preferred_common_name"), scientific)
            if value:
                output.append({
                    "name": value,
                    "language": locale,
                    "provider": "iNaturalist",
                    "source": "iNaturalist taxon names",
                    "url": f"https://www.inaturalist.org/taxa/{row.get('id')}",
                })
            break
    return output


LANGUAGE_ORDER = {"fr": 0, "fra": 0, "fre": 0, "en": 1, "eng": 1, "es": 2, "spa": 2, "pt": 3, "por": 3, "": 4}


def research_names(scientific: str, family: str) -> dict[str, Any]:
    gbif, key = gbif_names(scientific, family)
    rows = gbif + inat_names(scientific)
    rows.sort(key=lambda row: (LANGUAGE_ORDER.get(row.get("language", ""), 5), row["name"].casefold()))
    names: list[str] = []
    provenance: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        marker = row["name"].casefold()
        if marker in seen:
            continue
        seen.add(marker)
        names.append(row["name"])
        provenance.append(row)
        if len(names) >= 4:
            break
    return {"scientific_name": scientific, "names": names, "sources": provenance, "gbif_key": key}


def enrich_missing_names(files: list[tuple[Path, list[dict[str, Any]]]]) -> dict[str, Any]:
    profiles_by_path = {path: profiles for path, profiles in files}
    targets: list[tuple[Path, int, str, str]] = []
    total = 0
    missing_before = 0
    skipped_non_species: list[str] = []

    for path, profiles in files:
        for index, profile in enumerate(profiles):
            total += 1
            if vernacular_names(profile):
                continue
            missing_before += 1
            name = scientific_name(profile)
            if not name or name == "Inconnu" or "'" in name or "×" in name or name.endswith(" sp."):
                skipped_non_species.append(name or "Inconnu")
                continue
            family = str(taxonomy(profile).get("famille") or "").strip()
            targets.append((path, index, name, family))

    researched: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {executor.submit(research_names, name, family): name for _, _, name, family in targets}
        for future in as_completed(future_map):
            name = future_map[future]
            try:
                researched[name] = future.result()
            except Exception as exc:  # noqa: BLE001 - une API ne doit pas interrompre l'audit global
                researched[name] = {"scientific_name": name, "names": [], "sources": [], "error": str(exc)}

    changed_files: set[str] = set()
    resolved: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for path, index, name, _family in targets:
        result = researched.get(name, {})
        names = result.get("names") if isinstance(result, dict) else []
        if not names:
            unresolved.append(name)
            continue
        profile = profiles_by_path[path][index]
        profile.setdefault("taxonomie", {})["noms_vernaculaires"] = names
        changed_files.add(path.name)
        resolved.append(result)

    for path, profiles in files:
        if path.name in changed_files:
            path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "catalogue_profiles": total,
        "missing_before": missing_before,
        "researched_species": len(targets),
        "resolved": len(resolved),
        "remaining_without_attested_name": sorted(set(unresolved)),
        "non_species_without_name": sorted(set(skipped_non_species)),
        "changed_files": sorted(changed_files),
        "resolved_records": sorted(resolved, key=lambda item: item.get("scientific_name", "").casefold()),
    }


def main() -> int:
    source_files = [(path, profiles) for path, profiles in load_family_files() if path != OUTPUT_FILE]
    existing_names = {scientific_name(profile).split(" '", 1)[0] for _path, profiles in source_files for profile in profiles}
    generated = generate_selenicereus(existing_names)
    OUTPUT_FILE.write_text(json.dumps(generated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    files = load_family_files()
    audit = enrich_missing_names(files)
    cultivar_count = sum(1 for profile in generated if "'" in scientific_name(profile))
    audit.update({
        "generated_at": date.today().isoformat(),
        "selenicereus_accepted_species_target": len(ACCEPTED_SELENICEREUS),
        "selenicereus_species_added": sum(1 for profile in generated if "'" not in scientific_name(profile)),
        "pitaya_cultivars_added": cultivar_count,
        "pitaya_source_sets": {
            "UC_ANR": len(UCANR_CULTIVARS),
            "USDA_ARS_named_in_study": len(USDA_ARS_CULTIVARS),
            "Embrapa": len(EMBRAPA_CULTIVARS),
            "peer_reviewed_review": len(LITERATURE_CULTIVARS),
        },
        "sources": [POWO_GENUS, USDA_DRAGON_FRUIT, UCANR_SCI_NAMES, USDA_ARS_TRIAL, EMBRAPA_PITAYA, PITAYA_REVIEW],
    })
    REPORT_FILE.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"Selenicereus: {audit['selenicereus_species_added']} espèces ajoutées; "
        f"pitayas: {cultivar_count} cultivars/sélections ajoutés; "
        f"noms vernaculaires: {audit['resolved']}/{audit['missing_before']} fiches vides complétées."
    )
    if audit["remaining_without_attested_name"]:
        print(f"Espèces encore sans nom vernaculaire attesté: {len(audit['remaining_without_attested_name'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
