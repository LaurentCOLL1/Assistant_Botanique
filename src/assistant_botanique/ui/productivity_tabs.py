"""Tableau de bord, recherche globale et calendrier de soins."""
from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Callable, Mapping

from core import ValidationError, format_date_fr, parse_date
from assistant_botanique.domain.adaptive_care import recommend_care
from assistant_botanique.domain.care_types import (
    CARE_TYPES,
    QUICK_ACTION_LABELS,
    QUICK_ACTION_NOTES,
    SCHEDULABLE_CARE_TYPES,
    care_label,
)
from assistant_botanique.domain.search import SearchFilters, SearchResult, family_name, global_search
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.dashboard import DashboardItem, build_dashboard_snapshot
from assistant_botanique.services.planner import CarePlanner


def _record_quick_action(
    parent: tk.Misc,
    database: Database,
    plant_id: str | None,
    event_type: str,
    *,
    on_collection_refresh: Callable[[], None] | None = None,
    after: Callable[[], None] | None = None,
) -> None:
    if not plant_id:
        messagebox.showwarning("Soin", "Sélectionnez d'abord une plante.", parent=parent)
        return
    note = QUICK_ACTION_NOTES.get(event_type, care_label(event_type))
    if event_type in {"observation", "traitement"}:
        entered = simpledialog.askstring(
            QUICK_ACTION_LABELS.get(event_type, "Soin"),
            "Détail ou observation :",
            initialvalue="" if event_type == "observation" else note,
            parent=parent,
        )
        if entered is None:
            return
        note = entered.strip() or note
    database.add_care_event(plant_id, event_type, note=note)
    if on_collection_refresh:
        on_collection_refresh()
    if after:
        after()


class TodayDashboardTab(ttk.Frame):
    def __init__(
        self,
        parent,
        database: Database,
        profiles_by_id: Mapping[str, Mapping[str, Any]],
        *,
        on_collection_refresh: Callable[[], None] | None = None,
        on_open_calendar: Callable[[str | None], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.profiles_by_id = profiles_by_id
        self.on_collection_refresh = on_collection_refresh
        self.on_open_calendar = on_open_calendar
        self.planner = CarePlanner(database)
        self.items: dict[str, DashboardItem] = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        title = ttk.Frame(self)
        title.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(title, text="Aujourd'hui", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Button(title, text="Actualiser", command=self.refresh).pack(side="right")

        summary = ttk.Frame(self)
        summary.pack(fill="x", padx=12, pady=5)
        self.summary_vars: dict[str, tk.StringVar] = {}
        for key, label in (
            ("overdue", "En retard"),
            ("today", "Aujourd'hui"),
            ("week", "7 prochains jours"),
            ("events", "Soins cette semaine"),
        ):
            box = ttk.LabelFrame(summary, text=f" {label} ")
            box.pack(side="left", fill="x", expand=True, padx=4)
            variable = tk.StringVar(value="0")
            self.summary_vars[key] = variable
            ttk.Label(box, textvariable=variable, font=("Segoe UI", 18, "bold")).pack(padx=14, pady=10)

        ttk.Label(
            self,
            text=(
                "Les contrôles d'humidité sont proposés par le moteur adaptatif. Les autres soins sont des tâches "
                "que vous planifiez vous-même. Aucune action n'est exécutée automatiquement."
            ),
            wraplength=1150,
            justify="left",
        ).pack(fill="x", padx=16, pady=(3, 5))

        columns = ("date", "plant", "care", "status", "details")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        for column, label, width in (
            ("date", "Date", 100),
            ("plant", "Plante", 180),
            ("care", "Soin / contrôle", 180),
            ("status", "État", 130),
            ("details", "Détails", 420),
        ):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=12, pady=5)

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=12, pady=(3, 12))
        for event_type in ("substrat_sec", "encore_humide", "arrosage", "fertilisation", "observation"):
            ttk.Button(
                actions,
                text=QUICK_ACTION_LABELS[event_type],
                command=lambda key=event_type: self.record_action(key),
                style="Accent.TButton" if event_type == "arrosage" else None,
            ).pack(side="left", padx=3)
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=7)
        ttk.Button(actions, text="Terminer la tâche", command=self.complete_selected).pack(side="left", padx=3)
        ttk.Button(actions, text="Planifier un soin", command=self.open_calendar).pack(side="left", padx=3)

    def _selected_item(self) -> DashboardItem | None:
        selected = self.tree.selection()
        return self.items.get(selected[0]) if selected else None

    def selected_plant_id(self) -> str | None:
        item = self._selected_item()
        return item.plant_id if item else None

    def refresh(self) -> None:
        snapshot = build_dashboard_snapshot(self.database, self.profiles_by_id)
        self.summary_vars["overdue"].set(str(snapshot.overdue))
        self.summary_vars["today"].set(str(snapshot.today))
        self.summary_vars["week"].set(str(snapshot.next_seven_days))
        self.summary_vars["events"].set(str(snapshot.recent_events))
        current = self.tree.selection()[0] if self.tree.selection() else None
        self.tree.delete(*self.tree.get_children())
        self.items = {item.identifier: item for item in snapshot.items}
        for item in snapshot.items:
            self.tree.insert(
                "",
                "end",
                iid=item.identifier,
                values=(format_date_fr(item.due_date), item.plant_name, item.label, item.status, item.details),
            )
        if current and self.tree.exists(current):
            self.tree.selection_set(current)
        elif self.tree.get_children():
            self.tree.selection_set(self.tree.get_children()[0])

    def record_action(self, event_type: str) -> None:
        _record_quick_action(
            self,
            self.database,
            self.selected_plant_id(),
            event_type,
            on_collection_refresh=self.on_collection_refresh,
            after=self.refresh,
        )

    def complete_selected(self) -> None:
        item = self._selected_item()
        if not item:
            return
        if item.kind != "task":
            messagebox.showinfo(
                "Contrôle d'humidité",
                "Utilisez « Substrat sec », « Encore humide » ou « Arrosé » pour enregistrer le résultat du contrôle.",
                parent=self,
            )
            return
        self.planner.complete(item.identifier.split(":", 1)[1])
        if self.on_collection_refresh:
            self.on_collection_refresh()
        self.refresh()

    def open_calendar(self) -> None:
        if self.on_open_calendar:
            self.on_open_calendar(self.selected_plant_id())


class GlobalSearchTab(ttk.Frame):
    def __init__(
        self,
        parent,
        database: Database,
        catalogue: list[dict[str, Any]],
        profiles_by_id: Mapping[str, Mapping[str, Any]],
        *,
        on_navigate_catalogue: Callable[[str], None] | None = None,
        on_collection_refresh: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.catalogue = catalogue
        self.profiles_by_id = profiles_by_id
        self.on_navigate_catalogue = on_navigate_catalogue
        self.on_collection_refresh = on_collection_refresh
        self.results: dict[str, SearchResult] = {}
        self._build_ui()
        self.reload_filters()
        self.refresh()

    def _build_ui(self) -> None:
        filters = ttk.LabelFrame(self, text=" Recherche globale et filtres ")
        filters.pack(fill="x", padx=12, pady=(10, 5))
        filters.columnconfigure(1, weight=1)
        ttk.Label(filters, text="Recherche").grid(row=0, column=0, padx=5, pady=4, sticky="w")
        self.query = ttk.Entry(filters)
        self.query.grid(row=0, column=1, padx=5, pady=4, sticky="ew")
        self.query.bind("<KeyRelease>", lambda _event: self.refresh())
        ttk.Label(filters, text="Périmètre").grid(row=0, column=2, padx=5, pady=4)
        self.scope = ttk.Combobox(filters, state="readonly", width=14, values=("Tous", "Collection", "Catalogue"))
        self.scope.set("Tous")
        self.scope.grid(row=0, column=3, padx=5, pady=4)
        ttk.Label(filters, text="Famille").grid(row=1, column=0, padx=5, pady=4, sticky="w")
        self.family = ttk.Combobox(filters, state="readonly")
        self.family.grid(row=1, column=1, padx=5, pady=4, sticky="ew")
        ttk.Label(filters, text="Emplacement").grid(row=1, column=2, padx=5, pady=4)
        self.location = ttk.Combobox(filters, state="readonly", width=14)
        self.location.grid(row=1, column=3, padx=5, pady=4)
        ttk.Label(filters, text="Échéance").grid(row=2, column=0, padx=5, pady=4, sticky="w")
        self.due = ttk.Combobox(
            filters,
            state="readonly",
            values=("Tous", "En retard", "Aujourd'hui", "À venir", "Repos", "Fiche introuvable"),
        )
        self.due.set("Tous")
        self.due.grid(row=2, column=1, padx=5, pady=4, sticky="ew")
        ttk.Label(filters, text="Photos").grid(row=2, column=2, padx=5, pady=4)
        self.photos = ttk.Combobox(filters, state="readonly", width=14, values=("Toutes", "Avec photo", "Sans photo"))
        self.photos.set("Toutes")
        self.photos.grid(row=2, column=3, padx=5, pady=4)
        for widget in (self.scope, self.family, self.location, self.due, self.photos):
            widget.bind("<<ComboboxSelected>>", lambda _event: self.refresh())

        columns = ("kind", "title", "species", "family", "location", "status", "photo")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        for column, label, width in (
            ("kind", "Type", 90),
            ("title", "Nom", 180),
            ("species", "Espèce / détail", 230),
            ("family", "Famille", 130),
            ("location", "Emplacement", 110),
            ("status", "État", 120),
            ("photo", "Photo", 70),
        ):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=12, pady=5)
        self.tree.bind("<Double-1>", self.open_selected)

        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=12, pady=(3, 12))
        self.counter = ttk.Label(footer, text="0 résultat")
        self.counter.pack(side="left")
        ttk.Button(footer, text="Ouvrir", command=self.open_selected).pack(side="right", padx=3)
        for event_type in ("substrat_sec", "encore_humide", "arrosage", "observation"):
            ttk.Button(
                footer,
                text=QUICK_ACTION_LABELS[event_type],
                command=lambda key=event_type: self.record_action(key),
            ).pack(side="right", padx=3)

    def focus_search(self) -> None:
        self.query.focus_set()
        self.query.selection_range(0, tk.END)

    def reload_catalogue(
        self,
        catalogue: list[dict[str, Any]],
        profiles_by_id: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self.catalogue = catalogue
        self.profiles_by_id = profiles_by_id
        self.reload_filters()
        self.refresh()

    def reload_filters(self) -> None:
        families = sorted({family_name(profile) for profile in self.catalogue}, key=str.casefold)
        self.family["values"] = ("Toutes", *families)
        if self.family.get() not in self.family["values"]:
            self.family.set("Toutes")
        plants = self.database.load_plants()
        locations = sorted(
            {
                str((plant.get("contexte") or {}).get("emplacement") or "non renseigné")
                for plant in plants
                if isinstance(plant.get("contexte"), dict)
            },
            key=str.casefold,
        )
        self.location["values"] = ("Tous", *locations)
        if self.location.get() not in self.location["values"]:
            self.location.set("Tous")

    def _due_statuses(self) -> dict[str, str]:
        current = date.today()
        statuses: dict[str, str] = {}
        for plant in self.database.load_plants():
            profile = self.profiles_by_id.get(str(plant.get("species_id") or ""))
            if not profile:
                statuses[str(plant["id"])] = "Fiche introuvable"
                continue
            recommendation = recommend_care(profile, plant, today=current)
            if recommendation.next_check is None:
                status = "Repos"
            else:
                delta = (recommendation.next_check - current).days
                status = "En retard" if delta < 0 else "Aujourd'hui" if delta == 0 else "À venir"
            statuses[str(plant["id"])] = status
        for task in CarePlanner(self.database).due_tasks(current):
            statuses[str(task["plant_id"])] = "En retard" if task["due_date"] < current.isoformat() else "Aujourd'hui"
        return statuses

    def refresh(self) -> None:
        current = self.tree.selection()[0] if self.tree.selection() else None
        scope = {"Tous": "all", "Collection": "collection", "Catalogue": "catalogue"}.get(self.scope.get(), "all")
        photo_filter = {"Avec photo": "with", "Sans photo": "without"}.get(self.photos.get(), "")
        filters = SearchFilters(
            query=self.query.get(),
            scope=scope,
            family=self.family.get(),
            location=self.location.get(),
            due_status=self.due.get(),
            photo_status=photo_filter,
        )
        plants = self.database.load_plants()
        photo_ids = {str(item["plant_id"]) for item in self.database.list_photos()}
        matches = global_search(
            plants,
            self.catalogue,
            self.profiles_by_id,
            filters,
            due_status_by_plant=self._due_statuses(),
            photo_plant_ids=photo_ids,
        )
        self.tree.delete(*self.tree.get_children())
        self.results = {}
        for index, result in enumerate(matches):
            iid = f"{result.kind}:{result.identifier}:{index}"
            self.results[iid] = result
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    "Collection" if result.kind == "collection" else "Catalogue",
                    result.title,
                    result.subtitle,
                    result.family,
                    result.location,
                    result.status,
                    "Oui" if result.has_photo else "Non",
                ),
            )
        self.counter.configure(text=f"{len(matches)} résultat(s)")
        if current and self.tree.exists(current):
            self.tree.selection_set(current)
        elif self.tree.get_children():
            self.tree.selection_set(self.tree.get_children()[0])

    def selected_result(self) -> SearchResult | None:
        selected = self.tree.selection()
        return self.results.get(selected[0]) if selected else None

    def selected_plant_id(self) -> str | None:
        result = self.selected_result()
        return result.identifier if result and result.kind == "collection" else None

    def open_selected(self, _event=None) -> None:
        result = self.selected_result()
        if not result:
            return
        if result.kind == "catalogue" and self.on_navigate_catalogue:
            self.on_navigate_catalogue(result.identifier)
        elif result.kind == "collection":
            messagebox.showinfo(
                result.title,
                f"{result.subtitle}\nFamille : {result.family}\nEmplacement : {result.location}\nÉtat : {result.status}",
                parent=self,
            )

    def record_action(self, event_type: str) -> None:
        _record_quick_action(
            self,
            self.database,
            self.selected_plant_id(),
            event_type,
            on_collection_refresh=self.on_collection_refresh,
            after=self.refresh,
        )


class _TaskDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, plants: list[dict[str, Any]], selected_plant_id: str | None = None):
        super().__init__(parent)
        self.title("Planifier un soin")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.result: dict[str, Any] | None = None
        self.plants = plants
        self.plant_by_label = {
            f"{item.get('surnom', 'Sans nom')} — {item.get('species_id', '')}": str(item["id"])
            for item in plants
        }
        self.care_by_label = {item.label: item for item in SCHEDULABLE_CARE_TYPES}
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        labels = ("Plante", "Type de soin", "Date (JJ/MM/AAAA)", "Récurrence", "Note")
        for row, label in enumerate(labels):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=5)
        self.plant = ttk.Combobox(frame, state="readonly", width=45, values=tuple(self.plant_by_label))
        self.plant.grid(row=0, column=1, padx=4, pady=5)
        self.care = ttk.Combobox(frame, state="readonly", width=30, values=tuple(self.care_by_label))
        self.care.grid(row=1, column=1, padx=4, pady=5, sticky="ew")
        self.due = ttk.Entry(frame, width=20)
        self.due.grid(row=2, column=1, padx=4, pady=5, sticky="ew")
        self.due.insert(0, format_date_fr(date.today()))
        self.recurrence = ttk.Combobox(
            frame,
            state="readonly",
            values=("Aucune", "7 jours", "14 jours", "30 jours", "90 jours", "365 jours"),
        )
        self.recurrence.set("Aucune")
        self.recurrence.grid(row=3, column=1, padx=4, pady=5, sticky="ew")
        self.note = ttk.Entry(frame, width=45)
        self.note.grid(row=4, column=1, padx=4, pady=5, sticky="ew")
        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Annuler", command=self.destroy).pack(side="left", padx=3)
        ttk.Button(buttons, text="Planifier", command=self._submit, style="Accent.TButton").pack(side="left", padx=3)
        if self.plant_by_label:
            selected_label = next((label for label, identifier in self.plant_by_label.items() if identifier == selected_plant_id), None)
            self.plant.set(selected_label or next(iter(self.plant_by_label)))
        if self.care_by_label:
            self.care.set(next(iter(self.care_by_label)))
        self.care.bind("<<ComboboxSelected>>", self._care_changed)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()
        self.wait_visibility()
        self.focus_set()

    def _care_changed(self, _event=None) -> None:
        item = self.care_by_label.get(self.care.get())
        if item and item.default_recurrence_days:
            label = f"{item.default_recurrence_days} jours"
            if label in self.recurrence["values"]:
                self.recurrence.set(label)
        if item and not self.note.get():
            self.note.insert(0, item.default_note)

    def _submit(self) -> None:
        try:
            due = parse_date(self.due.get())
        except ValidationError as exc:
            messagebox.showerror("Date", str(exc), parent=self)
            return
        plant_id = self.plant_by_label.get(self.plant.get())
        care = self.care_by_label.get(self.care.get())
        if not plant_id or not care:
            messagebox.showwarning("Planification", "Sélectionnez une plante et un type de soin.", parent=self)
            return
        recurrence = None
        if self.recurrence.get() != "Aucune":
            recurrence = int(self.recurrence.get().split()[0])
        self.result = {
            "plant_id": plant_id,
            "care_type": care.key,
            "due_date": due,
            "note": self.note.get().strip() or care.default_note,
            "recurrence_days": recurrence,
        }
        self.destroy()


class CareCalendarTab(ttk.Frame):
    def __init__(
        self,
        parent,
        database: Database,
        profiles_by_id: Mapping[str, Mapping[str, Any]],
        *,
        on_collection_refresh: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.profiles_by_id = profiles_by_id
        self.on_collection_refresh = on_collection_refresh
        self.planner = CarePlanner(database)
        today = date.today()
        self.month = today.replace(day=1)
        self.rows: dict[str, dict[str, Any]] = {}
        self.preferred_plant_id: str | None = None
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=12, pady=(10, 5))
        ttk.Button(toolbar, text="◀", width=4, command=lambda: self.move_month(-1)).pack(side="left")
        ttk.Button(toolbar, text="Aujourd'hui", command=self.go_today).pack(side="left", padx=4)
        ttk.Button(toolbar, text="▶", width=4, command=lambda: self.move_month(1)).pack(side="left")
        self.month_label = ttk.Label(toolbar, text="", font=("Segoe UI", 15, "bold"))
        self.month_label.pack(side="left", padx=14)
        ttk.Label(toolbar, text="Type").pack(side="right", padx=(5, 3))
        self.type_filter = ttk.Combobox(toolbar, state="readonly", width=22)
        self.type_filter.pack(side="right")
        self.type_filter.bind("<<ComboboxSelected>>", lambda _event: self.refresh())

        columns = ("date", "plant", "care", "source", "status", "recurrence", "note")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        for column, label, width in (
            ("date", "Date", 95),
            ("plant", "Plante", 170),
            ("care", "Soin", 170),
            ("source", "Origine", 105),
            ("status", "État", 100),
            ("recurrence", "Récurrence", 95),
            ("note", "Note", 330),
        ):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=12, pady=5)

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=12, pady=(3, 12))
        ttk.Button(actions, text="Planifier un soin", command=self.add_task, style="Accent.TButton").pack(side="left", padx=3)
        ttk.Button(actions, text="Terminer", command=self.complete_selected).pack(side="left", padx=3)
        ttk.Button(actions, text="Reporter d'un jour", command=lambda: self.postpone_selected(1)).pack(side="left", padx=3)
        ttk.Button(actions, text="Reporter d'une semaine", command=lambda: self.postpone_selected(7)).pack(side="left", padx=3)
        ttk.Button(actions, text="Annuler la tâche", command=self.cancel_selected).pack(side="left", padx=3)
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=7)
        for event_type in ("fertilisation", "rempotage", "taille", "traitement"):
            ttk.Button(
                actions,
                text=QUICK_ACTION_LABELS[event_type],
                command=lambda key=event_type: self.record_action(key),
            ).pack(side="left", padx=3)

    def update_profiles(self, profiles_by_id: Mapping[str, Mapping[str, Any]]) -> None:
        self.profiles_by_id = profiles_by_id
        self.refresh()

    def select_plant(self, plant_id: str | None) -> None:
        self.preferred_plant_id = plant_id

    def move_month(self, offset: int) -> None:
        index = self.month.year * 12 + self.month.month - 1 + offset
        self.month = date(index // 12, index % 12 + 1, 1)
        self.refresh()

    def go_today(self) -> None:
        self.month = date.today().replace(day=1)
        self.refresh()

    def _month_bounds(self) -> tuple[date, date]:
        days = calendar.monthrange(self.month.year, self.month.month)[1]
        return self.month, self.month.replace(day=days)

    def _selected_row(self) -> dict[str, Any] | None:
        selected = self.tree.selection()
        return self.rows.get(selected[0]) if selected else None

    def selected_plant_id(self) -> str | None:
        row = self._selected_row()
        return str(row.get("plant_id")) if row else self.preferred_plant_id

    def refresh(self) -> None:
        self.month_label.configure(text=self.month.strftime("%B %Y").capitalize())
        labels = ("Tous", "Contrôle d'humidité", *(item.label for item in CARE_TYPES if item.key != "controle_humidite"))
        self.type_filter["values"] = labels
        if self.type_filter.get() not in labels:
            self.type_filter.set("Tous")
        start, end = self._month_bounds()
        rows: list[dict[str, Any]] = []
        for plant in self.database.load_plants():
            profile = self.profiles_by_id.get(str(plant.get("species_id") or ""))
            if not profile:
                continue
            recommendation = recommend_care(profile, plant, today=date.today())
            if recommendation.next_check and start <= recommendation.next_check <= end:
                rows.append(
                    {
                        "iid": f"check:{plant['id']}",
                        "kind": "check",
                        "plant_id": str(plant["id"]),
                        "date": recommendation.next_check,
                        "plant": str(plant.get("surnom") or "Sans nom"),
                        "care_type": "controle_humidite",
                        "care": "Contrôle d'humidité",
                        "source": "Adaptatif",
                        "status": "Prévu",
                        "recurrence": "Automatique",
                        "note": f"Confiance {recommendation.confidence_label}",
                    }
                )
        for task in self.planner.list_tasks(start=start, end=end, status=None):
            rows.append(
                {
                    "iid": f"task:{task['id']}",
                    "kind": "task",
                    "task_id": str(task["id"]),
                    "plant_id": str(task["plant_id"]),
                    "date": date.fromisoformat(task["due_date"]),
                    "plant": str(task.get("nickname") or "Sans nom"),
                    "care_type": str(task.get("care_type") or "soin"),
                    "care": care_label(str(task.get("care_type") or "soin")),
                    "source": "Planifié",
                    "status": {"pending": "À faire", "completed": "Terminé", "cancelled": "Annulé"}.get(task["status"], task["status"]),
                    "recurrence": f"{task['recurrence_days']} j" if task.get("recurrence_days") else "—",
                    "note": str(task.get("note") or ""),
                }
            )
        selected_type = self.type_filter.get()
        if selected_type != "Tous":
            rows = [row for row in rows if row["care"] == selected_type]
        rows.sort(key=lambda row: (row["date"], row["plant"].casefold(), row["care"].casefold()))
        current = self.tree.selection()[0] if self.tree.selection() else None
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        for index, row in enumerate(rows):
            iid = f"{row['iid']}:{index}"
            self.rows[iid] = row
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    format_date_fr(row["date"]),
                    row["plant"],
                    row["care"],
                    row["source"],
                    row["status"],
                    row["recurrence"],
                    row["note"],
                ),
            )
        if current and self.tree.exists(current):
            self.tree.selection_set(current)
        elif self.tree.get_children():
            self.tree.selection_set(self.tree.get_children()[0])

    def add_task(self) -> None:
        plants = self.database.load_plants()
        if not plants:
            messagebox.showwarning("Calendrier", "Ajoutez d'abord une plante à la collection.", parent=self)
            return
        dialog = _TaskDialog(self, plants, self.selected_plant_id())
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.planner.schedule(**dialog.result)
        self.preferred_plant_id = dialog.result["plant_id"]
        self.refresh()

    def complete_selected(self) -> None:
        row = self._selected_row()
        if not row:
            return
        if row["kind"] == "check":
            messagebox.showinfo(
                "Contrôle",
                "Enregistrez le résultat depuis l'onglet Aujourd'hui ou Recherche : substrat sec, encore humide ou arrosé.",
                parent=self,
            )
            return
        self.planner.complete(row["task_id"])
        if self.on_collection_refresh:
            self.on_collection_refresh()
        self.refresh()

    def postpone_selected(self, days: int) -> None:
        row = self._selected_row()
        if not row or row["kind"] != "task" or row["status"] != "À faire":
            messagebox.showwarning("Calendrier", "Sélectionnez une tâche en attente.", parent=self)
            return
        self.planner.postpone(row["task_id"], days)
        self.refresh()

    def cancel_selected(self) -> None:
        row = self._selected_row()
        if not row or row["kind"] != "task" or row["status"] != "À faire":
            return
        if messagebox.askyesno("Calendrier", "Annuler cette tâche planifiée ?", parent=self):
            self.planner.cancel(row["task_id"])
            self.refresh()

    def record_action(self, event_type: str) -> None:
        _record_quick_action(
            self,
            self.database,
            self.selected_plant_id(),
            event_type,
            on_collection_refresh=self.on_collection_refresh,
            after=self.refresh,
        )
