from pathlib import Path

from assistant_botanique.infrastructure.backup_config import BackupConfigRepository


def test_backup_config_is_created_with_default_directory(tmp_path: Path):
    config_path = tmp_path / "data" / "sauvegarde.ini"
    default_directory = tmp_path / "data" / "backups"
    repository = BackupConfigRepository(config_path, default_directory)

    directory = repository.load_directory()

    assert config_path.is_file()
    assert directory == default_directory.resolve()
    assert "[sauvegarde]" in config_path.read_text(encoding="utf-8")
    assert "dossier =" in config_path.read_text(encoding="utf-8")


def test_backup_config_reads_user_modified_directory(tmp_path: Path):
    config_path = tmp_path / "data" / "sauvegarde.ini"
    custom_directory = tmp_path / "external" / "botanical-backups"
    repository = BackupConfigRepository(config_path, tmp_path / "default")
    repository.ensure_exists()

    config_path.write_text(
        f"[sauvegarde]\ndossier = {custom_directory}\n",
        encoding="utf-8",
    )

    assert repository.load_directory() == custom_directory.resolve()
    assert custom_directory.is_dir()


def test_backup_config_resolves_relative_path_from_data_directory(tmp_path: Path):
    config_path = tmp_path / "data" / "sauvegarde.ini"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "[sauvegarde]\ndossier = mes-sauvegardes\n",
        encoding="utf-8",
    )
    repository = BackupConfigRepository(config_path, tmp_path / "default")

    assert repository.load_directory() == (config_path.parent / "mes-sauvegardes").resolve()
