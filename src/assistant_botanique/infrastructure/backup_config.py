"""Configuration utilisateur lisible du dossier de sauvegarde."""
from __future__ import annotations

import configparser
import os
import tempfile
from pathlib import Path

from assistant_botanique.paths import BACKUPS_DIR, DATA_DIR

BACKUP_CONFIG_FILE = DATA_DIR / "sauvegarde.ini"
SECTION = "sauvegarde"
DIRECTORY_KEY = "dossier"


class BackupConfigRepository:
    """Lit et écrit ``sauvegarde.ini`` sans imposer de modifier le code."""

    def __init__(
        self,
        path: Path = BACKUP_CONFIG_FILE,
        default_directory: Path = BACKUPS_DIR,
    ) -> None:
        self.path = Path(path)
        self.default_directory = Path(default_directory)

    def ensure_exists(self) -> Path:
        if not self.path.exists():
            self.save_directory(self.default_directory)
        return self.path

    def load_directory(self) -> Path:
        self.ensure_exists()
        parser = configparser.ConfigParser(interpolation=None)
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                parser.read_file(handle)
        except (OSError, configparser.Error) as exc:
            raise ValueError(f"Impossible de lire {self.path.name} : {exc}") from exc

        raw = parser.get(SECTION, DIRECTORY_KEY, fallback="").strip().strip('"')
        if not raw:
            directory = self.default_directory
        else:
            expanded = os.path.expandvars(os.path.expanduser(raw))
            directory = Path(expanded)
            if not directory.is_absolute():
                directory = self.path.parent / directory

        try:
            directory = directory.resolve()
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValueError(f"Le dossier de sauvegarde est inutilisable : {directory}\n{exc}") from exc
        return directory

    def save_directory(self, directory: Path | str) -> Path:
        directory = Path(os.path.expandvars(os.path.expanduser(str(directory).strip().strip('"'))))
        if not directory.is_absolute():
            directory = (self.path.parent / directory).resolve()
        else:
            directory = directory.resolve()

        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            "; Fichier modifiable dans le Bloc-notes.\n"
            "; Changez uniquement la valeur de 'dossier'.\n"
            "; Exemple : dossier = E:\\Sauvegardes\\AssistantBotanique\n"
            "; Les modifications sont relues à chaque sauvegarde ou restauration.\n\n"
            f"[{SECTION}]\n"
            f"{DIRECTORY_KEY} = {directory}\n"
        )

        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return self.path
