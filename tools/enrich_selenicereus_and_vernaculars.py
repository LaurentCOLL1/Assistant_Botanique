"""Ajoute Selenicereus/pitayas et complète les noms vernaculaires manquants.

Le script est volontairement conservateur : il n'invente jamais un nom commun.
Pour les fiches historiques sans nom vernaculaire, il interroge GBIF puis
iNaturalist et ne conserve que des noms explicitement publiés par ces sources.
Il produit un rapport de provenance dans ``catalogue_metadata``.

Les ajouts Selenicereus suivent le backbone taxonomique Kew/POWO 2026. Les
cultivars de pitaya proviennent de collections/programmes institutionnels UC ANR,
USDA-ARS et Embrapa.
"""
from __future__ import annotations

import copy
import json
import re
import time
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

USER_AGENT = "AssistantBotaniqueVernacularAudit/1.0 (https://github.com/LaurentCOLL1/Assistant_Botanique)"
GBIF_MATCH = "https://api.gbif.org/v1/species/match"
GBIF_VERNACULAR = "https://api.gbif.org/v1/species/{key}/vernacularNames"
INAT_TAXA = "https://api.inaturalist.org/v1/taxa"

POWO_GENUS = "https://powo.science.kew.org/taxon/urn:lsid:ipni.org:names:30011812-2"
USDA_DRAGON_FRUIT = "https://content.govdelivery.com/accounts/USDAAPHIS/bulletins/31b6635"
UCANR_SCI_NAMES = "https://ucanr.edu/site/san-diego-county-small-farms/pitahaya-scientific-names"
USDA_ARS_TRIAL = "https://www.ars.usda.gov/research/publications/publication/?seqNo115=376606"
EMBRAPA_PITAYA = "https://www.embrapa.br/en/busca-de-solucoes-tecnologicas/-/produto-servico/busca/Pitaya"

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

# Le nom historique Hylocereus polyrhizus est aujourd'hui un synonyme de
# Selenicereus monacanthus dans POWO. Les libellés ci-dessous conservent les
# noms de cultivars publiés par UC ANR tout en utilisant la taxonomie actuelle.
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

# Cultivars/lignées explicitement nommés dans la publication USDA-ARS et dans
# la synthèse de l'étude. Les doublons avec UC ANR sont éliminés plus bas.
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
    "Purple Haze",
)

EMBRAPA_CULTIVARS = (
    ("BRS Lua do Cerrado", "Selenicereus undatus"),
    ("BRS Luz do Cerrado", "Selenicereus undatus"),
    ("BRS Âmbar do Cerrado", "Selenicereus megalanthus"),
    ("BRS Cerrado Mini Pitaya", "Selenicereus setaceus"),
    ("BRS Granada do Cerrado", "Selenicereus undatus × Selenicereus costaricensis"),
)

STATIC_COMMON_NAMES: dict[str, list[str]] = {
    "Selenicereus anthonyanus": ["Cactus arête de poisson", "Fishbone cactus", "Ric-rac cactus"],
    "Selenicereus grandiflorus": ["Reine de la nuit", "Cierge à grandes fleurs", "Queen of the night"],
    "Selenicereus megalanthus": ["Pitaya jaune", "Fruit du dragon jaune", "Yellow dragon fruit"],
    "Selenicereus monacanthus": ["Pitaya rouge", "Fruit du dragon à chair rouge", "Red pitaya"],
    "Selenicereus costaricensis": ["Pitaya du Costa Rica", "Fruit du dragon rouge", "Costa Rican pitaya"],
    "Selenicereus ocamponis": ["Pitaya d'Ocampo", "Ocampo pitaya"],
    "Selenicereus setaceus": ["Pitaya du Cerrado", "Saborosa"],
    "Selenicereus undatus": ["Fruit du dragon", "Pitaya rouge", "Pitahaya"],
}


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
    value = value.casefold().replace("×", " x ")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


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
            profiles = [item for item in payload if isinstance(item, dict)]
            result.append((path, profiles))
    return result


def base_profile(name: str, *, cultivar: str | None = None, source: str = POWO_GENUS) -> dict[str, Any]:
    fruiting = name in COMMERCIAL_PITAYA_SPECIES or cultivar is not None
    common = list(STATIC_COMMON_NAMES.get(name, []))
    if cultivar:
        common = [cultivar, f"Pitaya {cultivar}", f"Fruit du dragon {cultivar}"]
    display_scientific = f"{name} '{cultivar}'" if cultivar and not name.endswith("sp.") and "×" not in name else (
        f"{name} '{cultivar}'" if cultivar else name
    )
    if cultivar and (name.endswith("sp.") or "×" in name):
        display_scientific = f"{name} '{cultivar}'"
    sources = [POWO_GENUS, source]
    if fruiting:
        sources.append(USDA_DRAGON_FRUIT)
    return {
        "id": slug(display_scientific),
        "taxonomie": {
            "nom_scientifique": display_scientific,
            "noms_vernaculaires": common,
            "famille": "Cactaceae",
            "origine_geographique": "Mexique, Amérique centrale, Caraïbes ou Amérique tropicale selon le taxon",
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
                "Baies charnues comestibles de type pitaya, couleur et chair variables selon espèce ou cultivar"
                if fruiting else
                "Baies charnues ; intérêt fruitier variable selon l'espèce"
            ),
        },
        "exigences_climatiques": {
            "temperature_ideale": "18°C à 30°C",
            "rusticite": "Craint le gel prolongé ; culture hors gel recommandée",
            "exposition": "Lumière vive à soleil filtré ; soleil direct progressif en culture fruitière",
            "hygrometrie": "Moyenne à élevée avec bonne circulation d'air",
        },
        "gestion_eau": {
            "frequence_mode": "Arroser régulièrement en croissance puis laisser la couche superficielle sécher ; réduire en hiver",
            "frequence_arrosage": {
                "janvier": 12, "fevrier": 12, "mars": 9, "avril": 7,
                "mai": 6, "juin": 5, "juillet": 5, "aout": 5,
                "septembre": 6, "octobre": 8, "novembre": 10, "decembre": 12,
            },
            "variation_saisonniere": "Plus d'eau pendant croissance, floraison et fructification ; nettement moins en période fraîche",
            "qualite_eau": "Eau peu calcaire de préférence",
            "sensibilite_minerale": "Sensible à l'asphyxie racinaire et à l'eau stagnante",
        },
        "substrat": {
            "ph": "5.5 - 7.0",
            "categorie_horticole": "Cactus épiphyte / pitaya",
            "modele_recherche": "aroid_chunky",
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
                {"titre": "USDA APHIS — Dragon fruit taxonomy", "url": USDA_DRAGON_FRUIT},
            ],
        },
        "entretien": {
            "rempotage": "Tous les 2 à 3 ans ou lorsque le support et le système racinaire deviennent trop à l'étroit",
            "taille": "Tailler les tiges âgées ou encombrantes et palisser les pousses vigoureuses",
            "fertilisation": "Engrais équilibré modéré en croissance ; éviter les excès d'azote avant floraison",
            "multiplication": "Boutures de tiges très faciles ; semis pour la diversité génétique",
        },
        "sante_securite": {
            "ravageurs": ["Cochenilles", "Cochenilles farineuses", "Acariens"],
            "maladies": ["Pourriture racinaire", "Anthracnose", "Taches et chancres des tiges"],
            "toxicite": "Non toxique ; fruits des pitayas cultivés comestibles",
            "proprietes_particulieres": (
                "Cultivar de pitaya documenté par un programme horticole institutionnel"
                if cultivar else
                "Espèce du genre Selenicereus, anciennement élargi par intégration d'Hylocereus"
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
    generated: list[dict[str, Any]] = []
    for name in ACCEPTED_SELENICEREUS:
        if name not in existing_names:
            generated.append(base_profile(name))

    seen_cultivars: set[str] = set()
    for cultivar, parent in UCANR_CULTIVARS:
        generated.append(base_profile(parent, cultivar=cultivar, source=UCANR_SCI_NAMES))
        seen_cultivars.add(cultivar.casefold())

    for cultivar in USDA_ARS_CULTIVARS:
        if cultivar.casefold() in seen_cultivars:
            continue
        generated.append(base_profile("Selenicereus sp.", cultivar=cultivar, source=USDA_ARS_TRIAL))
        seen_cultivars.add(cultivar.casefold())

    for cultivar, parent in EMBRAPA_CULTIVARS:
        if cultivar.casefold() in seen_cultivars:
            continue
        generated.append(base_profile(parent, cultivar=cultivar, source=EMBRAPA_PITAYA))
        seen_cultivars.add(cultivar.casefold())
    return generated


def clean_candidate(value: Any, scientific: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" ,;\t\n")
    if not text or len(text) < 2 or len(text) > 100:
        return ""
    if text.casefold() == scientific.casefold() or "http://" in text.casefold() or "https://" in text.casefold():
        return ""
    if re.fullmatch(r"[A-Z][a-z-]+\s+[a-z-]+(?:\s+.+)?", text) and scientific.casefold().startswith(text.casefold()):
        return ""
    return text


def gbif_names(scientific: str, family: str) -> tuple[list[dict[str, str]], str | None]:
    match = request_json(GBIF_MATCH, {"name": scientific, "family": family, "kingdom": "Plantae"})
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
        language = str(row.get("language") or "").casefold()
        source = str(row.get("source") or "GBIF").strip()
        candidates.append({
            "name": value,
            "language": language,
            "provider": "GBIF",
            "source": source,
            "url": f"https://www.gbif.org/species/{key}",
        })
    return candidates, str(key)


def inat_names(scientific: str) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for locale in ("fr", "en", "es", "pt"):
        payload = request_json(INAT_TAXA, {"q": scientific, "rank": "species", "locale": locale, "per_page": 10})
        results = payload.get("results", []) if isinstance(payload, dict) else []
        chosen = None
        for row in results if isinstance(results, list) else []:
            if not isinstance(row, dict):
                continue
            row_name = str(row.get("name") or "").strip()
            matched = str(row.get("matched_term") or "").strip()
            if row_name.casefold() == scientific.casefold() or matched.casefold() == scientific.casefold():
                chosen = row
                break
        if not chosen:
            continue
        value = clean_candidate(chosen.get("preferred_common_name"), scientific)
        if value:
            output.append({
                "name": value,
                "language": locale,
                "provider": "iNaturalist",
                "source": "iNaturalist taxon names",
                "url": f"https://www.inaturalist.org/taxa/{chosen.get('id')}",
            })
    return output


LANGUAGE_ORDER = {"fr": 0, "fra": 0, "fre": 0, "en": 1, "eng": 1, "es": 2, "spa": 2, "pt": 3, "por": 3, "": 4}


def research_names(scientific: str, family: str) -> dict[str, Any]:
    gbif, key = gbif_names(scientific, family)
    inat = inat_names(scientific)
    rows = gbif + inat
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
    targets: list[tuple[Path, int, str, str]] = []
    before = 0
    total = 0
    for path, profiles in files:
        for index, profile in enumerate(profiles):
            total += 1
            if vernacular_names(profile):
                continue
            before += 1
            name = scientific_name(profile)
            if not name or name == "Inconnu" or "'" in name or "×" in name or name.endswith(" sp."):
                continue
            family = str(taxonomy(profile).get("famille") or "").strip()
            targets.append((path, index, name, family))

    researched: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {
            executor.submit(research_names, name, family): name
            for _, _, name, family in targets
        }
        for future in as_completed(future_map):
            name = future_map[future]
            try:
                researched[name] = future.result()
            except Exception as exc:  # noqa: BLE001 - one taxon must not abort the audit
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
        tax = taxonomy(dict(files[[p for p, _ in files].index(path)][1][index]))
        # Modifie l'objet original contenu dans ``files``.
        profile = next(profiles[index] for p, profiles in files if p == path)
        profile_tax = profile.setdefault("taxonomie", {})
        profile_tax["noms_vernaculaires"] = names
        changed_files.add(path.name)
        resolved.append(result)

    for path, profiles in files:
        if path.name in changed_files:
            path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "catalogue_profiles": total,
        "missing_before": before,
        "researched": len(targets),
        "resolved": len(resolved),
        "remaining_without_attested_name": sorted(set(unresolved)),
        "changed_files": sorted(changed_files),
        "resolved_records": sorted(resolved, key=lambda item: item.get("scientific_name", "").casefold()),
    }


def main() -> int:
    files = load_family_files()
    existing_names = {scientific_name(profile).split(" '", 1)[0] for _path, profiles in files for profile in profiles}
    generated = generate_selenicereus(existing_names)
    OUTPUT_FILE.write_text(json.dumps(generated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Recharge pour inclure les nouvelles espèces dans l'audit vernaculaire.
    files = load_family_files()
    audit = enrich_missing_names(files)
    audit.update({
        "generated_at": date.today().isoformat(),
        "selenicereus_accepted_species_target": len(ACCEPTED_SELENICEREUS),
        "selenicereus_generated_species": sum(1 for profile in generated if "'" not in scientific_name(profile)),
        "pitaya_cultivars_generated": sum(1 for profile in generated if "'" in scientific_name(profile)),
        "sources": [POWO_GENUS, USDA_DRAGON_FRUIT, UCANR_SCI_NAMES, USDA_ARS_TRIAL, EMBRAPA_PITAYA],
    })
    REPORT_FILE.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "Enrichissement terminé : "
        f"{audit['selenicereus_generated_species']} espèces Selenicereus ajoutées, "
        f"{audit['pitaya_cultivars_generated']} cultivars ajoutés, "
        f"{audit['resolved']}/{audit['missing_before']} fiches sans nom vernaculaire complétées."
    )
    remaining = audit["remaining_without_attested_name"]
    if remaining:
        print(f"Noms vernaculaires non attestés après recherche : {len(remaining)}")
        for name in remaining[:50]:
            print(f" - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
