"""Point d'entrée de l'Assistant Botanique."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk

from app_data import CATALOGUE_ERRORS
from app_paths import LOG_FILE
from storage import SettingsRepository
from tab_catalogue import TabCatalogue
from tab_diagnostic import TabDiagnostic
from tab_gestion import TabGestion
from tab_substrat import TabSubstrat
from ui_theme import apply_theme

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    encoding="utf-8",
)
LOGGER = logging.getLogger(__name__)


class PlantCareApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings_repo = SettingsRepository()
        self.settings = self.settings_repo.load()
        self.theme = self.settings.get("theme", "light")

        self.root.title("Assistant Botanique — Soins, Substrats et suivi")
        self._configure_window()
        apply_theme(self.root, self.theme)
        self._build_menu()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        self.tab_catalogue = TabCatalogue(self.notebook)
        self.tab_substrat = TabSubstrat(self.notebook, settings=self.settings, on_settings_changed=self.save_settings)
        self.tab_gestion = TabGestion(
            self.notebook,
            on_collection_changed_callback=self.on_collection_updated,
            voir_catalogue_callback=self.navigate_to_catalogue,
        )
        self.tab_diagnostic = TabDiagnostic(self.notebook, collection_provider=lambda: self.tab_gestion.mes_plantes)

        self.notebook.add(self.tab_gestion, text="🪴 Collection & soins")
        self.notebook.add(self.tab_catalogue, text="📖 Catalogue")
        self.notebook.add(self.tab_substrat, text="🧪 Substrats")
        self.notebook.add(self.tab_diagnostic, text="🩺 Diagnostic")

        self.tab_substrat.actualiser_combo_substrat(self.tab_gestion.mes_plantes)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(400, self._show_catalogue_warnings)

    def _configure_window(self) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        default_w = min(1280, max(900, screen_w - 120))
        default_h = min(860, max(650, screen_h - 140))
        geometry = str(self.settings.get("geometry") or f"{default_w}x{default_h}")
        try:
            self.root.geometry(geometry)
        except tk.TclError:
            self.root.geometry(f"{default_w}x{default_h}")
        self.root.minsize(880, 620)

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)
        view_menu = tk.Menu(menu, tearoff=False)
        view_menu.add_command(label="Basculer mode clair/sombre", command=self.toggle_theme)
        menu.add_cascade(label="Affichage", menu=view_menu)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="Rapport de validation du catalogue", command=self.show_catalogue_report)
        menu.add_cascade(label="Aide", menu=help_menu)
        self.root.config(menu=menu)

    def toggle_theme(self) -> None:
        self.theme = "dark" if self.theme == "light" else "light"
        self.settings["theme"] = self.theme
        apply_theme(self.root, self.theme)
        self.save_settings()

    def on_collection_updated(self, plants: list[dict]) -> None:
        self.tab_substrat.actualiser_combo_substrat(plants)
        self.tab_diagnostic.refresh_plants()

    def navigate_to_catalogue(self, species_id: str) -> None:
        self.notebook.select(self.tab_catalogue)
        self.tab_catalogue.selectionner_plante(species_id)

    def save_settings(self) -> None:
        try:
            self.settings_repo.save(self.settings)
        except OSError:
            LOGGER.exception("Échec de sauvegarde des réglages")

    def _show_catalogue_warnings(self) -> None:
        if CATALOGUE_ERRORS:
            messagebox.showwarning(
                "Catalogue chargé avec avertissements",
                f"{len(CATALOGUE_ERRORS)} anomalie(s) ont été détectée(s). Consultez Aide > Rapport de validation.",
            )

    def show_catalogue_report(self) -> None:
        if not CATALOGUE_ERRORS:
            messagebox.showinfo("Validation", "Aucune anomalie de chargement détectée.")
            return
        messagebox.showwarning("Rapport de validation", "\n".join(CATALOGUE_ERRORS[:40]))

    def on_close(self) -> None:
        self.settings["geometry"] = self.root.geometry()
        self.save_settings()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    PlantCareApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
