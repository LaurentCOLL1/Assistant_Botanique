import json
from pathlib import Path

from assistant_botanique.infrastructure.catalogue import load_curated_metadata, merge_curated_metadata
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
