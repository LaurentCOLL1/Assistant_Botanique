"""Reclasse les fiches selon GBIF et complète les familles sous 20 espèces."""
from __future__ import annotations

import copy
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = ROOT / "familles_plantes"
META_DIR = ROOT / "catalogue_metadata"
AUDIT = META_DIR / "taxonomy_audit.json"
REPORT = META_DIR / "family_reclassification_report.md"
MATCH = "https://api.gbif.org/v1/species/match"
SEARCH = "https://api.gbif.org/v1/species/search"
HEADERS = {"User-Agent": "AssistantBotanique/3.0 family-maintenance", "Accept": "application/json"}
TARGET = 20
TODAY = datetime.now(timezone.utc).date().isoformat()

# Les candidats sont essayés dans cet ordre, puis complétés par les espèces GBIF
# ayant le plus d'occurrences. Chaque nom est revérifié par GBIF avant insertion.
EDIBLE = {
    "Aizoaceae": "Carpobrotus edulis|Tetragonia tetragonioides",
    "Amaranthaceae": "Amaranthus tricolor|Chenopodium album|Atriplex hortensis",
    "Annonaceae": "Annona macroprophyllata|Annona montana",
    "Apocynaceae": "Carissa macrocarpa",
    "Araceae": "Amorphophallus konjac|Xanthosoma sagittifolium",
    "Araliaceae": "Aralia elata|Centella asiatica|Panax ginseng",
    "Arecaceae": "Phoenix dactylifera|Cocos nucifera|Elaeis guineensis",
    "Asphodelaceae": "Hemerocallis fulva|Hemerocallis lilioasphodelus",
    "Asteraceae": "Lactuca sativa|Cynara cardunculus|Cichorium intybus|Helianthus annuus",
    "Bromeliaceae": "Ananas comosus|Bromelia pinguin",
    "Cactaceae": "Pereskia aculeata|Stenocereus thurberi|Myrtillocactus geometrizans",
    "Campanulaceae": "Platycodon grandiflorus|Campanula rapunculus",
    "Commelinaceae": "Commelina communis|Commelina benghalensis",
    "Crassulaceae": "Sedum sarmentosum|Hylotelephium spectabile",
    "Euphorbiaceae": "Manihot esculenta|Cnidoscolus aconitifolius",
    "Lamiaceae": "Ocimum basilicum|Mentha spicata|Salvia rosmarinus|Thymus vulgaris|Origanum vulgare|Salvia officinalis|Melissa officinalis|Perilla frutescens",
    "Malvaceae": "Abelmoschus esculentus|Theobroma cacao|Durio zibethinus|Hibiscus sabdariffa",
    "Marantaceae": "Maranta arundinacea|Calathea allouia",
    "Moraceae": "Ficus carica|Morus alba|Morus nigra|Artocarpus heterophyllus|Artocarpus altilis",
    "Orchidaceae": "Vanilla planifolia|Vanilla pompona",
    "Oxalidaceae": "Averrhoa carambola|Averrhoa bilimbi|Oxalis tuberosa",
    "Passifloraceae": "Passiflora ligularis|Passiflora maliformis|Passiflora laurifolia",
    "Piperaceae": "Piper nigrum|Piper longum|Piper betle|Piper methysticum",
    "Ranunculaceae": "Nigella sativa",
    "Rubiaceae": "Coffea canephora|Coffea liberica|Morinda citrifolia",
    "Sapindaceae": "Nephelium lappaceum|Dimocarpus longan|Acer saccharum",
    "Solanaceae": "Solanum tuberosum|Solanum melongena|Physalis philadelphica|Physalis peruviana|Lycium barbarum",
    "Urticaceae": "Urtica dioica|Urtica urens|Boehmeria nivea",
    "Verbenaceae": "Lippia graveolens|Phyla dulcis",
    "Vitaceae": "Vitis vinifera|Vitis labrusca|Vitis rotundifolia|Cissus quadrangularis",
    "Zingiberaceae": "Zingiber officinale|Curcuma longa|Alpinia galanga|Kaempferia galanga|Zingiber mioga",
}
CULTIVATED = {
    "Acanthaceae": "Justicia brandegeeana|Crossandra infundibuliformis|Thunbergia alata|Ruellia simplex|Acanthus mollis",
    "Aizoaceae": "Lithops aucampiae|Lithops lesliei|Delosperma cooperi|Faucaria tigrina",
    "Apocynaceae": "Plumeria rubra|Nerium oleander|Catharanthus roseus|Trachelospermum jasminoides|Vinca minor|Hoya kerrii",
    "Araceae": "Philodendron gloriosum|Caladium bicolor|Alocasia odora|Anthurium crystallinum|Syngonium podophyllum",
    "Araliaceae": "Eleutherococcus senticosus|Tetrapanax papyrifer|Schefflera actinophylla|Polyscias scutellaria",
    "Arecaceae": "Areca catechu|Syagrus romanzoffiana|Washingtonia robusta|Trachycarpus fortunei|Livistona chinensis",
    "Asphodelaceae": "Aloe ferox|Aristaloe aristata|Aloe polyphylla|Haworthia cooperi|Gasteria verrucosa",
    "Asteraceae": "Calendula officinalis|Echinacea purpurea|Dahlia pinnata|Zinnia elegans|Tagetes patula|Gerbera jamesonii",
    "Begoniaceae": "Begonia cucullata|Begonia boliviensis|Begonia luxurians|Begonia bowerae|Begonia metallica|Begonia grandis",
    "Bignoniaceae": "Handroanthus impetiginosus|Tabebuia rosea|Spathodea campanulata|Pandorea jasminoides|Tecoma capensis",
    "Bromeliaceae": "Tillandsia cyanea|Tillandsia xerographica|Aechmea chantinii|Alcantarea imperialis|Puya alpestris",
    "Cactaceae": "Gymnocalycium mihanovichii|Astrophytum myriostigma|Ferocactus latispinus|Rebutia minuscula|Mammillaria elongata",
    "Campanulaceae": "Lobelia erinus|Lobelia cardinalis|Campanula lactiflora|Campanula pyramidalis|Trachelium caeruleum",
    "Commelinaceae": "Tradescantia fluminensis|Tradescantia sillamontana|Tradescantia virginiana|Dichorisandra thyrsiflora|Callisia fragrans",
    "Costaceae": "Costus barbatus|Costus spiralis|Costus speciosus|Costus pictus|Costus afer|Chamaecostus cuspidatus",
    "Crassulaceae": "Aeonium arboreum|Sempervivum tectorum|Graptopetalum paraguayense|Kalanchoe pinnata|Echeveria agavoides|Sedum rubrotinctum",
    "Cycadaceae": "Cycas rumphii|Cycas taitungensis|Cycas debaoensis|Cycas panzhihuaensis|Cycas thouarsii",
    "Droseraceae": "Drosera adelae|Drosera burmannii|Drosera filiformis|Drosera intermedia|Drosera rotundifolia",
    "Euphorbiaceae": "Ricinus communis|Jatropha curcas|Acalypha wilkesiana|Euphorbia lactea|Euphorbia tirucalli",
    "Gesneriaceae": "Primulina dryas|Kohleria amabilis|Streptocarpus saxorum|Sinningia leucotricha|Aeschynanthus speciosus",
    "Hydrangeaceae": "Hydrangea aspera|Hydrangea involucrata|Hydrangea heteromalla|Schizophragma hydrangeoides|Carpenteria californica",
    "Lamiaceae": "Lavandula angustifolia|Nepeta cataria|Pogostemon cablin|Agastache foeniculum|Monarda didyma",
    "Lentibulariaceae": "Pinguicula esseriana|Pinguicula gigantea|Pinguicula laueana|Utricularia sandersonii|Utricularia longifolia",
    "Magnoliaceae": "Magnolia champaca|Magnolia figo|Magnolia virginiana|Magnolia acuminata|Magnolia officinalis",
    "Malvaceae": "Gossypium hirsutum|Alcea rosea|Malva sylvestris|Ceiba speciosa|Hibiscus syriacus",
    "Marantaceae": "Goeppertia lancifolia|Goeppertia roseopicta|Goeppertia zebrina|Ctenanthe setosa|Thalia dealbata",
    "Melastomataceae": "Pleroma heteromallum|Pleroma granulosum|Medinilla cummingii|Miconia calvescens|Tibouchina granulosa",
    "Moraceae": "Ficus religiosa|Ficus benghalensis|Ficus pumila|Ficus deltoidea|Maclura pomifera|Dorstenia foetida",
    "Nepenthaceae": "Nepenthes ventricosa|Nepenthes veitchii|Nepenthes rafflesiana|Nepenthes ampullaria|Nepenthes truncata|Nepenthes maxima|Nepenthes rajah",
    "Orchidaceae": "Cattleya labiata|Paphiopedilum insigne|Vanda coerulea|Phalaenopsis amabilis|Ludisia discolor|Bletilla striata",
    "Oxalidaceae": "Oxalis versicolor|Oxalis corniculata|Oxalis stricta|Oxalis adenophylla|Oxalis articulata",
    "Passifloraceae": "Passiflora coccinea|Passiflora racemosa|Passiflora lutea|Passiflora foetida|Passiflora mixta",
    "Pinaceae": "Abies nordmanniana|Cedrus atlantica|Larix decidua|Tsuga canadensis|Pseudotsuga menziesii",
    "Piperaceae": "Peperomia polybotrya|Peperomia clusiifolia|Peperomia graveolens|Peperomia rotundifolia|Piper auritum",
    "Ranunculaceae": "Clematis montana|Aconitum napellus|Pulsatilla vulgaris|Thalictrum aquilegiifolium|Eranthis hyemalis",
    "Rubiaceae": "Cinchona officinalis|Gardenia thunbergia|Ixora chinensis|Hamelia patens|Luculia gratissima",
    "Sapindaceae": "Dodonaea viscosa|Acer griseum|Acer japonicum|Acer negundo|Aesculus parviflora",
    "Scrophulariaceae": "Buddleja davidii|Buddleja globosa|Nemesia strumosa|Diascia barberae|Verbascum thapsus|Scrophularia nodosa|Leucophyllum frutescens",
    "Solanaceae": "Datura stramonium|Nicotiana alata|Nicandra physalodes|Solanum pseudocapsicum|Brunfelsia pauciflora",
    "Urticaceae": "Boehmeria cylindrica|Pilea involucrata|Pilea mollis|Elatostema repens|Pellionia repens|Parietaria judaica",
    "Verbenaceae": "Verbena bonariensis|Verbena officinalis|Glandularia canadensis|Lantana montevidensis|Vitex trifolia",
    "Violaceae": "Viola labradorica|Viola canadensis|Viola pubescens|Viola biflora|Viola pedata",
    "Vitaceae": "Parthenocissus quinquefolia|Parthenocissus tricuspidata|Ampelopsis glandulosa|Cissus rhombifolia|Vitis amurensis",
    "Zamiaceae": "Dioon edule|Dioon spinulosum|Encephalartos altensteinii|Encephalartos ferox|Macrozamia communis|Ceratozamia mexicana|Zamia integrifolia",
    "Zingiberaceae": "Hedychium gardnerianum|Etlingera elatior|Curcuma alismatifolia|Globba winitii|Alpinia purpurata|Zingiber spectabile",
}
EDIBLE = {key: value.split("|") for key, value in EDIBLE.items()}
CULTIVATED = {key: value.split("|") for key, value in CULTIVATED.items()}


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def slug(family: str) -> str:
    return normalized(family).replace("-", "_") + ".json"


def name(profile: dict[str, Any]) -> str:
    return clean((profile.get("taxonomie") or {}).get("nom_scientifique"))


def family(profile: dict[str, Any]) -> str:
    return clean((profile.get("taxonomie") or {}).get("famille"))


def request_json(url: str, params: dict[str, Any]) -> dict[str, Any] | None:
    request = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers=HEADERS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 or (exc.code != 429 and exc.code < 500):
                return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(attempt + 1)
    return None


def match(scientific_name: str, rank: str | None = None) -> dict[str, Any] | None:
    params: dict[str, Any] = {"name": scientific_name, "strict": "true", "verbose": "true"}
    if rank:
        params["rank"] = rank
    result = request_json(MATCH, params)
    return result if isinstance(result, dict) and result.get("matchType") != "NONE" else None


def verified_candidate(scientific_name: str, expected_family: str) -> dict[str, Any] | None:
    result = match(scientific_name, "SPECIES")
    if not result or clean(result.get("family")).casefold() != expected_family.casefold():
        return None
    if int(result.get("confidence") or 0) < 92:
        return None
    canonical = clean(result.get("canonicalName") or result.get("scientificName") or scientific_name)
    if len(canonical.split()) < 2 or any(token in canonical.casefold() for token in (" spp", " sp.", " aff.", " cf.")):
        return None
    return {"name": canonical, "family": expected_family, "key": result.get("acceptedUsageKey") or result.get("usageKey"), "occurrences": 0}


def gbif_species(expected_family: str) -> list[dict[str, Any]]:
    family_match = match(expected_family, "FAMILY") or {}
    family_key = family_match.get("acceptedUsageKey") or family_match.get("usageKey")
    if not isinstance(family_key, int):
        return []
    found: dict[str, dict[str, Any]] = {}
    offset = 0
    while offset < 3000:
        result = request_json(SEARCH, {"highertaxon_key": family_key, "rank": "SPECIES", "status": "ACCEPTED", "limit": 1000, "offset": offset}) or {}
        page = result.get("results", [])
        if not page:
            break
        for item in page:
            canonical = clean(item.get("canonicalName") or item.get("scientificName"))
            if clean(item.get("family")).casefold() == expected_family.casefold() and len(canonical.split()) == 2 and "×" not in canonical:
                found[normalized(canonical)] = {"name": canonical, "family": expected_family, "key": item.get("nubKey") or item.get("key"), "occurrences": int(item.get("numOccurrences") or 0)}
        if result.get("endOfRecords") or len(page) < 1000:
            break
        offset += len(page)
    return sorted(found.values(), key=lambda item: (-item["occurrences"], item["name"].casefold()))


def choose_template(items: list[dict[str, Any]], scientific_name: str) -> dict[str, Any]:
    genus = scientific_name.split()[0].casefold()
    return next((profile for profile in items if name(profile).split()[0].casefold() == genus), items[0])


def provisional_profile(template: dict[str, Any], candidate: dict[str, Any], priority: str) -> dict[str, Any]:
    profile = copy.deepcopy(template)
    taxonomy = profile.setdefault("taxonomie", {})
    taxonomy.update(nom_scientifique=candidate["name"], noms_vernaculaires=[], famille=candidate["family"], origine_geographique="À documenter — identité taxonomique vérifiée par GBIF")
    health = profile.setdefault("sante_securite", {})
    health["toxicite"] = "À vérifier spécifiquement ; ne pas ingérer sans validation botanique et sanitaire."
    health["proprietes_particulieres"] = "Fiche taxonomique ajoutée automatiquement ; données horticoles provisoires."
    profile["conseil"] = "Profil horticole provisoire extrapolé d'une espèce apparentée. Vérifier ce taxon avant culture ou consommation."
    sources = profile.get("sources") if isinstance(profile.get("sources"), list) else []
    sources.append({"titre": "GBIF Backbone Taxonomy", "url": f"https://www.gbif.org/species/{candidate['key']}" if candidate.get("key") else "https://www.gbif.org/species/search", "type": "taxonomie", "consulte_le": TODAY})
    profile["sources"] = sources
    profile["validation_catalogue"] = {"taxonomie": "GBIF", "gbif_key": candidate.get("key"), "ajoute_le": TODAY, "priorite": priority, "horticulture": "provisoire_a_reviser"}
    return profile


def main() -> int:
    files = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in sorted(FAMILY_DIR.glob("*.json"))}
    originals = set(files)
    audit = json.loads(AUDIT.read_text(encoding="utf-8")).get("profiles", {}) if AUDIT.exists() else {}
    moves: list[tuple[str, str, str]] = []
    for items in files.values():
        for profile in items:
            audited = audit.get(normalized(name(profile)), {})
            taxonomic = audited.get("taxonomic", {}) if isinstance(audited, dict) else {}
            if taxonomic.get("status") != "family_mismatch" and taxonomic.get("family_consistent") is not False:
                continue
            old_family = family(profile)
            fresh = match(name(profile), "SPECIES") or {}
            new_family = clean(fresh.get("family") or taxonomic.get("family"))
            if new_family and new_family.casefold() != old_family.casefold():
                profile.setdefault("taxonomie", {})["famille"] = new_family
                moves.append((name(profile), old_family, new_family))

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for items in files.values():
        for profile in items:
            if family(profile):
                groups[family(profile)].append(profile)
    for family_name, items in list(groups.items()):
        unique: dict[str, dict[str, Any]] = {}
        for profile in items:
            key = normalized(name(profile))
            previous = unique.get(key)
            if previous is None or len(profile.get("sources", [])) > len(previous.get("sources", [])):
                unique[key] = profile
        groups[family_name] = list(unique.values())

    existing = {normalized(name(profile)) for items in groups.values() for profile in items}
    additions: list[tuple[str, str, str, Any]] = []
    limitations: list[tuple[str, int]] = []
    for family_name in sorted(groups, key=str.casefold):
        items = groups[family_name]
        if len(items) < TARGET:
            ordered: list[tuple[str, str]] = []
            ordered.extend((candidate, "comestible") for candidate in EDIBLE.get(family_name, []))
            ordered.extend((candidate, "cultivee") for candidate in CULTIVATED.get(family_name, []))
            for scientific_name, priority in ordered:
                if len(items) >= TARGET or normalized(scientific_name) in existing:
                    continue
                candidate = verified_candidate(scientific_name, family_name)
                if candidate and normalized(candidate["name"]) not in existing:
                    items.append(provisional_profile(choose_template(items, candidate["name"]), candidate, priority))
                    existing.add(normalized(candidate["name"]))
                    additions.append((family_name, candidate["name"], priority, candidate.get("key")))
            if len(items) < TARGET:
                for candidate in gbif_species(family_name):
                    if len(items) >= TARGET:
                        break
                    if normalized(candidate["name"]) in existing:
                        continue
                    items.append(provisional_profile(choose_template(items, candidate["name"]), candidate, "gbif_frequente"))
                    existing.add(normalized(candidate["name"]))
                    additions.append((family_name, candidate["name"], "gbif_frequente", candidate.get("key")))
        if len(items) < TARGET:
            limitations.append((family_name, len(items)))

    final = {slug(family_name): sorted(items, key=lambda profile: (1 if isinstance(profile.get("validation_catalogue"), dict) else 0, name(profile).casefold())) for family_name, items in groups.items()}
    for filename, items in final.items():
        (FAMILY_DIR / filename).write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    deleted = sorted(originals - set(final))
    for filename in deleted:
        path = FAMILY_DIR / filename
        if path.exists():
            path.unlink()

    lines = ["# Reclassement GBIF et enrichissement des familles", "", f"Généré le {datetime.now(timezone.utc).isoformat(timespec='seconds')}.", "", "## Résumé", "", f"- Reclassements : **{len(moves)}**", f"- Fichiers consolidés/supprimés : **{len(deleted)}**", f"- Espèces ajoutées : **{len(additions)}**", f"- Familles à au moins {TARGET} espèces : **{sum(len(items) >= TARGET for items in groups.values())}/{len(groups)}**", f"- Familles restant sous {TARGET} : **{len(limitations)}**", "", "## Reclassements", ""]
    lines.extend([f"- **{species}** : {old} → {new}" for species, old, new in sorted(moves)] or ["- Aucun."])
    lines.extend(["", "## Fichiers supprimés ou consolidés", ""])
    lines.extend([f"- `{filename}`" for filename in deleted] or ["- Aucun."])
    lines.extend(["", "## Espèces ajoutées", ""])
    lines.extend([f"- **{family_name}** — {species} (`{priority}`, GBIF {key or 'sans clé'})" for family_name, species, priority, key in sorted(additions)] or ["- Aucune."])
    lines.extend(["", f"## Familles restant sous {TARGET} espèces", ""])
    lines.extend([f"- **{family_name}** : {count} espèce(s)" for family_name, count in limitations] or ["- Aucune."])
    lines.extend(["", "## Prudence", "", "Les identités taxonomiques ajoutées sont validées par GBIF. Les données horticoles copiées depuis une espèce apparentée sont explicitement provisoires et doivent être revues avant toute prescription de culture ou de consommation."])
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"moves={len(moves)} deleted={len(deleted)} additions={len(additions)} limitations={len(limitations)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
