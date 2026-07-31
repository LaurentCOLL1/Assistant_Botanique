import json
from pathlib import Path


def load_family(filename: str) -> list[dict]:
    return json.loads((Path("familles_plantes") / filename).read_text(encoding="utf-8"))


def by_name(profiles: list[dict], scientific_name: str) -> dict:
    return next(
        profile
        for profile in profiles
        if profile.get("taxonomie", {}).get("nom_scientifique") == scientific_name
    )


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

    portulacaria = by_name(load_family("aizoaceae_portulacaceae.json"), "Portulacaria afra")
    anacampseros = by_name(load_family("aizoaceae_portulacaceae.json"), "Anacampseros rufescens")
    zamia = by_name(load_family("cycadaceae_zamiaceae.json"), "Zamia furfuracea")
    polygonatum = by_name(load_family("polygonaceae.json"), "Polygonatum multiflorum")
    assert portulacaria["taxonomie"]["famille"] == "Didiereaceae"
    assert anacampseros["taxonomie"]["famille"] == "Anacampserotaceae"
    assert zamia["taxonomie"]["famille"] == "Zamiaceae"
    assert polygonatum["taxonomie"]["famille"] == "Asparagaceae"


def test_full_taxonomy_audit_covers_every_profile():
    payload = json.loads(Path("catalogue_metadata/taxonomy_audit.json").read_text(encoding="utf-8"))
    profiles = payload["profiles"]

    assert len(profiles) == 2204
    assert all(item["structure"]["complete"] is True for item in profiles.values())
    assert all(item.get("scientific_name") for item in profiles.values())
    assert all(item.get("source_file") for item in profiles.values())


def test_photo_catalogue_has_traceable_open_licenses():
    payload = json.loads(Path("catalogue_metadata/photos.json").read_text(encoding="utf-8"))
    profiles = payload["profiles"]
    illustrated = [
        item for item in profiles.values()
        if item.get("status") in {"found", "representative"}
    ]

    assert len(profiles) == 2204
    assert len(illustrated) >= 2180
    assert len(illustrated) / len(profiles) >= 0.98
    for item in illustrated:
        assert item.get("image_url")
        assert item.get("page_url")
        assert item.get("license")
        license_text = item["license"].casefold()
        assert "by-nc" not in license_text
        assert "by-nd" not in license_text
        assert "noncommercial" not in license_text
        assert "no derivatives" not in license_text
