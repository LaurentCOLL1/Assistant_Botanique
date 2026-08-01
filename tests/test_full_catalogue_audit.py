import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


SMALL_FAMILY_LIMITS = {
    "Cephalotaceae": 1,
    "Dioncophyllaceae": 3,
    "Mystropetalaceae": 4,
}


def load_family(filename: str) -> list[dict]:
    return json.loads((Path("familles_plantes") / filename).read_text(encoding="utf-8"))


def by_name(profiles: list[dict], scientific_name: str) -> dict:
    return next(
        profile
        for profile in profiles
        if profile.get("taxonomie", {}).get("nom_scientifique") == scientific_name
    )


def slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_") + ".json"


def source_profiles() -> list[dict]:
    return [
        profile
        for path in sorted(Path("familles_plantes").glob("*.json"))
        for profile in json.loads(path.read_text(encoding="utf-8"))
    ]


def identifiers(profiles: list[dict]) -> list[str]:
    values = []
    counts: Counter[str] = Counter()
    for profile in profiles:
        name = profile["taxonomie"]["nom_scientifique"]
        identifier = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()).strip("-")
        counts[identifier] += 1
        values.append(identifier if counts[identifier] == 1 else f"{identifier}--duplicate-{counts[identifier]}")
    return values


def test_certain_catalogue_anomalies_are_fixed():
    ananas = by_name(load_family("bromeliaceae.json"), "Ananas comosus 'Variegatus'")
    ananas_months = ananas["gestion_eau"]["frequence_arrosage"]
    assert ananas_months["avril"] == 7
    assert "april" not in ananas_months

    lily = by_name(load_family("liliaceae.json"), "Lilium martagon")
    lily_months = lily["gestion_eau"]["frequence_arrosage"]
    assert lily_months["juillet"] == 4
    assert "jullet" not in lily_months

    lime = by_name(load_family("tiliaceae.json"), "Tilia tuan")
    lime_months = lime["gestion_eau"]["frequence_arrosage"]
    assert lime_months["avril"] == 1
    assert "april" not in lime_months

    portulacaria = by_name(load_family("didiereaceae.json"), "Portulacaria afra")
    anacampseros = by_name(load_family("anacampserotaceae.json"), "Anacampseros rufescens")
    zamia = by_name(load_family("zamiaceae.json"), "Zamia furfuracea")
    polygonatum = by_name(load_family("asparagaceae.json"), "Polygonatum multiflorum")
    assert portulacaria["taxonomie"]["famille"] == "Didiereaceae"
    assert anacampseros["taxonomie"]["famille"] == "Anacampserotaceae"
    assert zamia["taxonomie"]["famille"] == "Zamiaceae"
    assert polygonatum["taxonomie"]["famille"] == "Asparagaceae"


def test_one_canonical_file_per_family_and_target_counts():
    seen_families: set[str] = set()
    for path in sorted(Path("familles_plantes").glob("*.json")):
        profiles = json.loads(path.read_text(encoding="utf-8"))
        assert profiles
        families = {profile["taxonomie"]["famille"] for profile in profiles}
        assert len(families) == 1
        family = next(iter(families))
        assert family not in seen_families
        seen_families.add(family)
        assert path.name == slug(family)
        if family in SMALL_FAMILY_LIMITS:
            assert len(profiles) == SMALL_FAMILY_LIMITS[family]
        else:
            assert len(profiles) >= 20


def test_full_taxonomy_audit_covers_every_profile_without_family_mismatch():
    source = source_profiles()
    payload = json.loads(Path("catalogue_metadata/taxonomy_audit.json").read_text(encoding="utf-8"))
    profiles = payload["profiles"]

    assert len(source) >= 2204
    assert set(profiles) == set(identifiers(source))
    assert all(item["structure"]["complete"] is True for item in profiles.values())
    assert all(item.get("scientific_name") for item in profiles.values())
    assert all(item.get("source_file") for item in profiles.values())
    assert all(item["taxonomic"].get("status") != "family_mismatch" for item in profiles.values())
    assert all(item["taxonomic"].get("family_consistent") is not False for item in profiles.values())


def test_provisional_additions_are_traceable_and_cautious():
    provisional = [
        profile
        for profile in source_profiles()
        if isinstance(profile.get("validation_catalogue"), dict)
    ]
    assert provisional
    for profile in provisional:
        validation = profile["validation_catalogue"]
        assert validation["taxonomie"] == "GBIF"
        assert validation["gbif_key"]
        assert validation["horticulture"] == "provisoire_a_reviser"
        assert any(source.get("titre") == "GBIF Backbone Taxonomy" for source in profile.get("sources", []))
        assert "provisoire" in profile.get("conseil", "").casefold()
        assert "vérifier" in profile["sante_securite"]["toxicite"].casefold()


def test_photo_catalogue_covers_source_and_keeps_licenses_traceable():
    source = source_profiles()
    payload = json.loads(Path("catalogue_metadata/photos.json").read_text(encoding="utf-8"))
    profiles = payload["profiles"]
    illustrated = [item for item in profiles.values() if item.get("status") in {"found", "representative"}]

    assert set(profiles) == set(identifiers(source))
    # Le reclassement et la déduplication ont conservé plus de 2 100 images
    # sourcées. Les nouvelles fiches sont volontairement laissées sans image
    # plutôt que d'associer une photographie incertaine.
    assert len(illustrated) >= 2100
    for item in illustrated:
        assert item.get("image_url")
        assert item.get("page_url")
        assert item.get("license")
        license_text = item["license"].casefold()
        assert "by-nc" not in license_text
        assert "by-nd" not in license_text
        assert "noncommercial" not in license_text
        assert "no derivatives" not in license_text
