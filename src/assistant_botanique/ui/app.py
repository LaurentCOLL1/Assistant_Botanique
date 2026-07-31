"""Fenêtre principale version 3, avec compatibilité des onglets historiques."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk

from app_data import (
    CATALOGUE_ERRORS,
    DATABASE_BY_ID,
    DATABASE_PLANTES,
    reload_catalogue,
)
from app_paths import LOG_FILE
from assistant_botanique.infrastructure.settings import SettingsRepository
from assistant_botanique.services.notifications import NotificationService
from assistant_botanique.ui.v3_tabs import AdaptiveCareTab, CatalogueReviewTab, MaintenanceTab, PhotoTimelineTab
from storage import CollectionRepository
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
        self.database = CollectionRepository().database
        self.notifications = NotificationService()

        self.root.title("Assistant Botanique 3 — Soins adaptatifs et journal")
        self._configure_window()
        apply_theme(self.root, self.theme)
        self._build_menu()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        self.tab_gestion = TabGestion(
            self.notebook,
            on_collection_changed_callback=self.on_collection_updated,
            voir_catalogue_callback=self.navigate_to_catalogue,
        )
        self.tab_catalogue = TabCatalogue(self.notebook)
        self.tab_substrat = TabSubstrat(self.notebook, settings=self.settings, on_settings_changed=self.save_settings)
        self.tab_diagnostic = TabDiagnostic(self.notebook, collection_provider=lambda: self.tab_gestion.mes_plantes)
        self.tab_adaptive = AdaptiveCareTab(
            self.notebook,
            self.database,
            DATABASE_BY_ID,
            on_collection_refresh=self.refresh_legacy_collection,
        )
        self.tab_photos = PhotoTimelineTab(self.notebook, self.database)
        self.tab_review = CatalogueReviewTab(
            self.notebook,
            self.database,
            DATABASE_PLANTES,
            reload_catalogue=self.reload_catalogue_views,
        )
        self.tab_maintenance = MaintenanceTab(self.notebook, self.database, self.settings_repo, self.settings)

        tabs = (
            (self.tab_gestion, "🪴 Collection"),
            (self.tab_adaptive, "🌦️ Soins adaptatifs"),
            (self.tab_photos, "📷 Journal & photos"),
            (self.tab_catalogue, "📖 Catalogue"),
            (self.tab_review, "✅ Révision botanique"),
            (self.tab_substrat, "🧪 Substrats"),
            (self.tab_diagnostic, "🩺 Diagnostic"),
            (self.tab_maintenance, "🛠️ Sauvegarde & système"),
        )
        for widget, label in tabs:
            self.notebook.add(widget, text=label)

        self.tab_substrat.actualiser_combo_substrat(self.tab_gestion.mes_plantes)
        self.notebook.bind("<<NotebookTabChanged>>", self._tab_changed)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(500, self._show_catalogue_warnings)
        self.root.after(1200, self.notify_due_items)

    def _configure_window(self) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        default_w = min(1400, max(980, screen_w - 80))
        default_h = min(920, max(680, screen_h - 100))
        geometry = str(self.settings.get("geometry") or f"{default_w}x{default_h}")
        try:
            self.root.geometry(geometry)
        except tk.TclError:
            self.root.geometry(f"{default_w}x{default_h}")
        self.root.minsize(920, 650)

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)
        view_menu = tk.Menu(menu, tearoff=False)
        view_menu.add_command(label="Basculer mode clair/sombre", command=self.toggle_theme)
        menu.add_cascade(label="Affichage", menu=view_menu)
        tools = tk.Menu(menu, tearoff=False)
        tools.add_command(label="Afficher les contrôles du jour", command=self.notify_due_items)
        tools.add_command(label="Recharger les données botaniques", command=self.reload_catalogue_views)
        menu.add_cascade(label="Outils", menu=tools)
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
        if hasattr(self, "tab_adaptive"):
            self.tab_adaptive.refresh()
        if hasattr(self, "tab_photos"):
            self.tab_photos.refresh_plants()
        if hasattr(self, "tab_maintenance"):
            self.tab_maintenance.refresh_stats()

    def refresh_legacy_collection(self) -> None:
        self.tab_gestion._load_collection()
        self.on_collection_updated(self.tab_gestion.mes_plantes)

    def navigate_to_catalogue(self, species_id: str) -> None:
        self.notebook.select(self.tab_catalogue)
        self.tab_catalogue.selectionner_plante(species_id)

    def reload_catalogue_views(self) -> None:
        reload_catalogue()
        self.tab_adaptive.profiles_by_id = DATABASE_BY_ID
        self.tab_adaptive.refresh()
        try:
            self.tab_catalogue.appliquer_filtres()
        except AttributeError:
            pass

    def _tab_changed(self, _event=None) -> None:
        selected = self.notebook.nametowidget(self.notebook.select())
        if selected is self.tab_adaptive:
            self.tab_adaptive.refresh()
        elif selected is self.tab_photos:
            self.tab_photos.refresh_plants()
        elif selected is self.tab_maintenance:
            self.tab_maintenance.refresh_stats()

    def notify_due_items(self) -> None:
        if not self.settings.get("notifications", {}).get("enabled", True):
            return
        try:
            self.notifications.notify_due(self.database, DATABASE_BY_ID)
        except Exception:
            LOGGER.exception("Impossible d'afficher les notifications")

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
        messagebox.showwarning("Rapport de validation", "\n".join(CATALOGUE_ERRORS[:60]))

    def on_close(self) -> None:
        self.settings["geometry"] = self.root.geometry()
        self.save_settings()
        self.root.destroy()


def run_gui() -> None:
    root = tk.Tk()
    PlantCareApp(root)
    root.mainloop()
