"""Fenêtre principale version 3 avec modes simple et avancé."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk

from app_data import CATALOGUE_ERRORS, DATABASE_BY_ID, DATABASE_PLANTES, reload_catalogue
from app_paths import LOG_FILE
from assistant_botanique.domain.ui_mode import normalized_ui_mode, visible_tab_keys
from assistant_botanique.infrastructure.settings import SettingsRepository
from assistant_botanique.services.notifications import NotificationService
from assistant_botanique.ui.collection_editor_tab import CollectionEditorTab
from assistant_botanique.ui.v3_tabs import (
    AdaptiveCareTab,
    CareCalendarTab,
    CatalogueReviewTab,
    GlobalSearchTab,
    MaintenanceTab,
    PhotoTimelineTab,
    TodayDashboardTab,
)
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
        self.ui_mode = normalized_ui_mode(self.settings.get("ui_mode"))
        self.database = CollectionRepository().database
        self.notifications = NotificationService()

        self.root.title("Assistant Botanique 3 — Tableau de bord et soins")
        self._configure_window()
        apply_theme(self.root, self.theme)
        self._build_menu()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)
        self._create_tabs()
        self._apply_ui_mode()

        self.tab_substrat.actualiser_combo_substrat(self.tab_gestion.mes_plantes)
        self.notebook.bind("<<NotebookTabChanged>>", self._tab_changed)
        self.root.bind_all("<Control-k>", self.open_global_search)
        self.root.bind_all("<Control-K>", self.open_global_search)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(500, self._show_catalogue_warnings)
        self.root.after(1200, self.notify_due_items)

    def _configure_window(self) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        default_w = min(1500, max(1020, screen_w - 80))
        default_h = min(950, max(700, screen_h - 100))
        geometry = str(self.settings.get("geometry") or f"{default_w}x{default_h}")
        try:
            self.root.geometry(geometry)
        except tk.TclError:
            self.root.geometry(f"{default_w}x{default_h}")
        self.root.minsize(960, 680)

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)
        view_menu = tk.Menu(menu, tearoff=False)
        view_menu.add_command(label="Basculer mode clair/sombre", command=self.toggle_theme)
        view_menu.add_separator()
        self.mode_var = tk.StringVar(value=self.ui_mode)
        view_menu.add_radiobutton(
            label="Mode simple",
            variable=self.mode_var,
            value="simple",
            command=lambda: self.set_ui_mode("simple"),
        )
        view_menu.add_radiobutton(
            label="Mode avancé",
            variable=self.mode_var,
            value="advanced",
            command=lambda: self.set_ui_mode("advanced"),
        )
        menu.add_cascade(label="Affichage", menu=view_menu)

        tools = tk.Menu(menu, tearoff=False)
        tools.add_command(label="Recherche globale (Ctrl+K)", command=self.open_global_search)
        tools.add_command(label="Afficher les contrôles du jour", command=self.notify_due_items)
        tools.add_command(label="Recharger les données botaniques", command=self.reload_catalogue_views)
        menu.add_cascade(label="Outils", menu=tools)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="Rapport de validation du catalogue", command=self.show_catalogue_report)
        menu.add_cascade(label="Aide", menu=help_menu)
        self.root.config(menu=menu)

    def _create_tabs(self) -> None:
        self.tab_today = TodayDashboardTab(
            self.notebook,
            self.database,
            DATABASE_BY_ID,
            on_collection_refresh=self.refresh_legacy_collection,
            on_open_calendar=self.open_calendar,
        )
        self.tab_gestion = TabGestion(
            self.notebook,
            on_collection_changed_callback=self.on_collection_updated,
            voir_catalogue_callback=self.navigate_to_catalogue,
        )
        self.tab_editor = CollectionEditorTab(
            self.notebook,
            self.database,
            DATABASE_PLANTES,
            on_collection_refresh=self.refresh_legacy_collection,
        )
        self.tab_search = GlobalSearchTab(
            self.notebook,
            self.database,
            DATABASE_PLANTES,
            DATABASE_BY_ID,
            on_navigate_catalogue=self.navigate_to_catalogue,
            on_collection_refresh=self.refresh_legacy_collection,
        )
        self.tab_calendar = CareCalendarTab(
            self.notebook,
            self.database,
            DATABASE_BY_ID,
            on_collection_refresh=self.refresh_legacy_collection,
        )
        self.tab_adaptive = AdaptiveCareTab(
            self.notebook,
            self.database,
            DATABASE_BY_ID,
            on_collection_refresh=self.refresh_legacy_collection,
        )
        self.tab_photos = PhotoTimelineTab(self.notebook, self.database)
        self.tab_catalogue = TabCatalogue(self.notebook)
        self.tab_review = CatalogueReviewTab(
            self.notebook,
            self.database,
            DATABASE_PLANTES,
            reload_catalogue=self.reload_catalogue_views,
        )
        self.tab_substrat = TabSubstrat(
            self.notebook,
            settings=self.settings,
            on_settings_changed=self.save_settings,
        )
        self.tab_diagnostic = TabDiagnostic(
            self.notebook,
            collection_provider=lambda: self.tab_gestion.mes_plantes,
        )
        self.tab_maintenance = MaintenanceTab(
            self.notebook,
            self.database,
            self.settings_repo,
            self.settings,
            on_data_changed=self.refresh_legacy_collection,
        )

        self.tabs_by_key = {
            "today": (self.tab_today, "🏠 Aujourd'hui"),
            "collection": (self.tab_gestion, "🪴 Collection"),
            "editor": (self.tab_editor, "✏️ Modifier collection"),
            "search": (self.tab_search, "🔎 Recherche"),
            "calendar": (self.tab_calendar, "📅 Calendrier"),
            "adaptive": (self.tab_adaptive, "🌦️ Soins adaptatifs"),
            "photos": (self.tab_photos, "📷 Journal & photos"),
            "catalogue": (self.tab_catalogue, "📖 Catalogue"),
            "review": (self.tab_review, "✅ Révision botanique"),
            "substrate": (self.tab_substrat, "🧪 Substrats"),
            "diagnostic": (self.tab_diagnostic, "🩺 Diagnostic guidé"),
            "maintenance": (self.tab_maintenance, "🛠️ Données & système"),
        }

    def _apply_ui_mode(self) -> None:
        current_widget = None
        selected = self.notebook.select()
        if selected:
            try:
                current_widget = self.notebook.nametowidget(selected)
            except (KeyError, tk.TclError):
                current_widget = None
        for tab_id in self.notebook.tabs():
            self.notebook.forget(tab_id)
        visible = visible_tab_keys(self.ui_mode)
        for key in visible:
            widget, label = self.tabs_by_key[key]
            self.notebook.add(widget, text=label)
        visible_widgets = {self.tabs_by_key[key][0] for key in visible}
        if current_widget in visible_widgets:
            self.notebook.select(current_widget)
        else:
            self.notebook.select(self.tab_today)
        suffix = "Mode simple" if self.ui_mode == "simple" else "Mode avancé"
        self.root.title(f"Assistant Botanique 3 — {suffix}")

    def set_ui_mode(self, mode: str) -> None:
        self.ui_mode = normalized_ui_mode(mode)
        self.mode_var.set(self.ui_mode)
        self.settings["ui_mode"] = self.ui_mode
        self.save_settings()
        self._apply_ui_mode()

    def toggle_theme(self) -> None:
        self.theme = "dark" if self.theme == "light" else "light"
        self.settings["theme"] = self.theme
        apply_theme(self.root, self.theme)
        self.save_settings()

    def on_collection_updated(self, plants: list[dict]) -> None:
        self.tab_substrat.actualiser_combo_substrat(plants)
        self.tab_diagnostic.refresh_plants()
        self.tab_editor.refresh()
        self.tab_adaptive.refresh()
        self.tab_photos.refresh_plants()
        self.tab_today.refresh()
        self.tab_search.reload_filters()
        self.tab_search.refresh()
        self.tab_calendar.refresh()
        self.tab_maintenance.refresh_stats()

    def refresh_legacy_collection(self) -> None:
        self.tab_gestion._load_collection()
        self.on_collection_updated(self.tab_gestion.mes_plantes)

    def navigate_to_catalogue(self, species_id: str) -> None:
        self.notebook.select(self.tab_catalogue)
        self.tab_catalogue.selectionner_plante(species_id)

    def open_global_search(self, _event=None) -> str:
        self.notebook.select(self.tab_search)
        self.tab_search.focus_search()
        return "break"

    def open_calendar(self, plant_id: str | None = None) -> None:
        self.tab_calendar.select_plant(plant_id)
        self.notebook.select(self.tab_calendar)

    def reload_catalogue_views(self) -> None:
        reload_catalogue()
        self.tab_adaptive.profiles_by_id = DATABASE_BY_ID
        self.tab_today.profiles_by_id = DATABASE_BY_ID
        self.tab_calendar.update_profiles(DATABASE_BY_ID)
        self.tab_search.reload_catalogue(DATABASE_PLANTES, DATABASE_BY_ID)
        self.tab_adaptive.refresh()
        try:
            self.tab_catalogue.filtrer_catalogue()
        except AttributeError:
            try:
                self.tab_catalogue.appliquer_filtres()
            except AttributeError:
                pass

    def _tab_changed(self, _event=None) -> None:
        selected_id = self.notebook.select()
        if not selected_id:
            return
        selected = self.notebook.nametowidget(selected_id)
        if selected is self.tab_today:
            self.tab_today.refresh()
        elif selected is self.tab_editor:
            self.tab_editor.refresh()
        elif selected is self.tab_search:
            self.tab_search.refresh()
        elif selected is self.tab_calendar:
            self.tab_calendar.refresh()
        elif selected is self.tab_adaptive:
            self.tab_adaptive.refresh()
        elif selected is self.tab_photos:
            self.tab_photos.refresh_plants()
        elif selected is self.tab_diagnostic:
            self.tab_diagnostic.refresh_plants()
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
        self.settings["ui_mode"] = self.ui_mode
        self.save_settings()
        self.root.destroy()


def run_gui() -> None:
    root = tk.Tk()
    PlantCareApp(root)
    root.mainloop()
