import json
from pathlib import Path

from assistant_botanique.infrastructure.catalogue import (
    load_catalogue,
    load_curated_metadata,
    load_generated_profile_map,
    merge_curated_metadata,
)
from validate_data import audit_directory, load_notable_species

MONTHS = {
    "janvier", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
}


def test_curated_metadata_is_merged_without_overwriting_explicit_values(tmp_path: Path):
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    (metadata_dir / "araceae.json").write_text(
        json.dumps(
            {
                "arum-creticum": {
                    "sources": ["https://example.org/taxonomy"],
                    "confidence": "moyenne",
                    "review_status": "a_verifier",
                }
            }
        ),
        encoding="utf-8",
    )
    curated = load_curated_metadata(metadata_dir)
    profile = {
        "taxonomie": {"nom_scientifique": "Arum creticum"},
        "metadata": {"confidence": "elevee"},
    }

    merged = merge_curated_metadata(profile, curated)

    assert merged["metadata"]["sources"] == ["https://example.org/taxonomy"]
    assert merged["metadata"]["confidence"] == "elevee"
    assert "metadata" not in profile or profile["metadata"] == {"confidence": "elevee"}


def test_generated_files_are_not_mistaken_for_curated_metadata(tmp_path: Path):
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    payload = {"schema_version": 1, "profiles": {"arum-creticum": {"status": "found"}}}
    (metadata_dir / "photos.json").write_text(json.dumps(payload), encoding="utf-8")
    (metadata_dir / "taxonomy_audit.json").write_text(json.dumps(payload), encoding="utf-8")

    assert load_curated_metadata(metadata_dir) == {}
    assert load_generated_profile_map(metadata_dir / "photos.json") == {
        "arum-creticum": {"status": "found"}
    }


def test_generated_photo_and_taxonomy_audit_are_attached(tmp_path: Path):
    families = tmp_path / "families"
    metadata = tmp_path / "metadata"
    families.mkdir()
    metadata.mkdir()
    profile = {
        "taxonomie": {
            "nom_scientifique": "Arum creticum",
            "noms_vernaculaires": ["Arum de Crète"],
            "famille": "Araceae",
            "origine_geographique": "Crète",
        },
        "morphologie": {},
        "exigences_climatiques": {},
        "gestion_eau": {"frequence_arrosage": {month: 0 for month in MONTHS}},
        "substrat": {},
        "entretien": {},
        "sante_securite": {"toxicite": "Toxique"},
    }
    (families / "araceae.json").write_text(json.dumps([profile]), encoding="utf-8")
    (metadata / "photos.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": {
                    "arum-creticum": {
                        "status": "found",
                        "page_url": "https://commons.wikimedia.org/wiki/File:Arum.jpg",
                        "license": "CC BY-SA 4.0",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (metadata / "taxonomy_audit.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": {
                    "arum-creticum": {
                        "taxonomic": {"status": "accepted_exact", "family": "Araceae"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    catalogue, errors = load_catalogue(families, metadata)

    assert not errors
    assert catalogue[0]["photo"]["status"] == "found"
    assert catalogue[0]["catalogue_audit"]["taxonomic"]["status"] == "accepted_exact"


def test_notable_species_registry_reports_missing_species(tmp_path: Path):
    families = tmp_path / "families"
    metadata = tmp_path / "metadata"
    families.mkdir()
    metadata.mkdir()
    (families / "araceae.json").write_text(
        json.dumps(
            [
                {
                    "taxonomie": {
                        "nom_scientifique": "Arum creticum",
                        "noms_vernaculaires": ["Arum de Crète"],
                        "famille": "Araceae",
                    },
                    "gestion_eau": {"frequence_arrosage": {month: 0 for month in MONTHS}},
                }
            ]
        ),
        encoding="utf-8",
    )
    notable = metadata / "notable_species.json"
    notable.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "families": {
                    "Araceae": {
                        "species": ["Arum creticum", "Arum italicum"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    errors, warnings = audit_directory(families, metadata, notable)

    assert not errors
    assert any("Arum italicum" in warning for warning in warnings)
    assert load_notable_species(notable)["Araceae"] == {"Arum creticum", "Arum italicum"}


def test_araceae_complements_are_complete_and_sourced():
    paths = [
        Path("familles_plantes/araceae_arum.json"),
        Path("familles_plantes/araceae_notables.json"),
    ]
    profiles = [
        profile
        for path in paths
        for profile in json.loads(path.read_text(encoding="utf-8"))
    ]
    names = {profile["taxonomie"]["nom_scientifique"] for profile in profiles}

    assert {"Arum creticum", "Arum italicum", "Arum maculatum"} <= names
    for profile in profiles:
        assert set(profile["gestion_eau"]["frequence_arrosage"]) == MONTHS
        assert profile["metadata"]["sources"]
        assert profile["metadata"]["last_reviewed"] == "2026-07-31"
        assert profile["metadata"]["review_status"] == "valide"
