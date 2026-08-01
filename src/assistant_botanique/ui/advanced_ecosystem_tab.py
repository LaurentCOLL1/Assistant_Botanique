"""Atelier avancé : QR, actions groupées, généalogie, stock, environnement et taxonomie."""
from __future__ import annotations

import secrets
import threading
import tkinter as tk
import webbrowser
from datetime import date
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable, Mapping

from core import format_date_fr, scientific_name
from assistant_botanique.infrastructure.advanced_repository import AdvancedRepository
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.infrastructure.settings import SettingsRepository
from assistant_botanique.services.labels import LabelService
from assistant_botanique.services.local_web import LocalCompanionServer
from assistant_botanique.services.notifications import NotificationService
from assistant_botanique.services.sensor_import import SensorImportService
from assistant_botanique.services.taxonomy_diff import TaxonomyDiffService
from assistant_botanique.services.weather import WeatherService, outdoor_care_advisories


class AdvancedEcosystemTab(ttk.Frame):
    BULK_ACTIONS = (
        "substrat_sec",
        "encore_humide",
        "arrosage",
        "fertilisation",
        "rempotage",
        "taille",
        "traitement",
        "rotation",
        "nettoyage",
        "observation",
    )

    def __init__(
        self,
        parent,
        database: Database,
        profiles_by_id: Mapping[str, Mapping[str, Any]],
        settings: dict[str, Any],
        settings_repo: SettingsRepository,
        *,
        on_collection_refresh: Callable[[], None] | None = None,
        reload_catalogue: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.profiles_by_id = profiles_by_id
        self.settings = settings
        self.settings_repo = settings_repo
        self.on_collection_refresh = on_collection_refresh
        self.reload_catalogue = reload_catalogue
        self.repository = AdvancedRepository(database)
        self.labels = LabelService()
        self.weather = WeatherService()
        self.taxonomy = TaxonomyDiffService(database)
        self.notifications = NotificationService()
        self.companion: LocalCompanionServer | None = None
        self.plants: list[dict[str, Any]] = []
        self.plant_by_label: dict[str, dict[str, Any]] = {}
        self._build_ui()
        self.refresh()

    def destroy(self) -> None:
        if self.companion:
            self.companion.stop()
        super().destroy()

    def _build_ui(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(header, text="Atelier avancé", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(
            header,
            text="Toutes les opérations sensibles demandent une validation et restent locales.",
        ).pack(side="left", padx=14)
        ttk.Button(header, text="Actualiser", command=self.refresh).pack(side="right")
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self._build_labels_tab()
        self._build_bulk_tab()
        self._build_propagation_tab()
        self._build_inventory_tab()
        self._build_treatments_tab()
        self._build_notifications_tab()
        self._build_environment_tab()
        self._build_taxonomy_tab()

    def _add_tab(self, title: str) -> ttk.Frame:
        frame = ttk.Frame(self.tabs)
        self.tabs.add(frame, text=title)
        return frame

    def _plant_label(self, plant: Mapping[str, Any]) -> str:
        profile = self.profiles_by_id.get(str(plant.get("species_id") or ""), {})
        return f"{plant.get('surnom', 'Sans nom')} — {scientific_name(profile) if profile else plant.get('species_id', '')}"

    def _build_labels_tab(self) -> None:
        tab = self._add_tab("🏷️ QR & compagnon")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        ttk.Label(
            tab,
            text=(
                "Sélectionnez les plantes à étiqueter. Le compagnon web écoute uniquement sur "
                "cet ordinateur par défaut ; l'accès réseau local doit être activé explicitement."
            ),
            wraplength=1050,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        self.label_tree = ttk.Treeview(
            tab,
            columns=("nickname", "species", "location"),
            show="headings",
            selectmode="extended",
        )
        for key, title, width in (
            ("nickname", "Surnom", 180),
            ("species", "Espèce", 280),
            ("location", "Emplacement", 160),
        ):
            self.label_tree.heading(key, text=title)
            self.label_tree.column(key, width=width)
        self.label_tree.grid(row=1, column=0, sticky="nsew", padx=10, pady=4)
        controls = ttk.Frame(tab)
        controls.grid(row=2, column=0, sticky="ew", padx=10, pady=8)
        ttk.Button(controls, text="Tout sélectionner", command=self._select_all_labels).pack(side="left", padx=3)
        ttk.Button(
            controls,
            text="Créer la feuille d'étiquettes",
            command=self._generate_labels,
            style="Accent.TButton",
        ).pack(side="left", padx=3)
        ttk.Separator(controls, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(controls, text="Démarrer sur cet ordinateur", command=lambda: self._start_companion(False)).pack(side="left", padx=3)
        ttk.Button(controls, text="Activer sur le réseau local", command=lambda: self._start_companion(True)).pack(side="left", padx=3)
        ttk.Button(controls, text="Arrêter", command=self._stop_companion).pack(side="left", padx=3)
        ttk.Button(controls, text="Ouvrir", command=self._open_companion).pack(side="left", padx=3)
        self.companion_status = ttk.Label(tab, text="Compagnon arrêté")
        self.companion_status.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))

    def _select_all_labels(self) -> None:
        self.label_tree.selection_set(self.label_tree.get_children())

    def _selected_label_plants(self) -> list[dict[str, Any]]:
        selected = set(self.label_tree.selection())
        return [plant for plant in self.plants if plant["id"] in selected]

    def _generate_labels(self) -> None:
        plants = self._selected_label_plants()
        if not plants:
            messagebox.showwarning("Étiquettes", "Sélectionnez au moins une plante.", parent=self)
            return
        destination = filedialog.asksaveasfilename(
            title="Enregistrer la feuille d'étiquettes",
            defaultextension=".html",
            filetypes=(("Page HTML imprimable", "*.html"),),
            initialfile=f"etiquettes-plantes-{date.today():%Y%m%d}.html",
            parent=self,
        )
        if not destination:
            return
        base_url = self.companion.base_url if self.companion and self.companion.running else None
        token = self.companion.token if self.companion and self.companion.running else None
        try:
            result = self.labels.generate_printable_sheet(
                plants,
                self.profiles_by_id,
                destination,
                base_url=base_url,
                companion_token=token,
            )
        except (OSError, RuntimeError) as exc:
            messagebox.showerror("Étiquettes", str(exc), parent=self)
            return
        webbrowser.open(result.as_uri())
        messagebox.showinfo("Étiquettes", f"Feuille créée :\n{result}", parent=self)

    def _companion_token(self) -> str:
        config = self.settings.setdefault("companion", {})
        token = str(config.get("token") or "")
        if not token:
            token = secrets.token_urlsafe(24)
            config["token"] = token
            self.settings_repo.save(self.settings)
        return token

    def _start_companion(self, lan: bool) -> None:
        if lan and not messagebox.askyesno(
            "Compagnon réseau local",
            (
                "Le compagnon sera accessible aux appareils du même réseau disposant du lien et du jeton. "
                "N'activez pas cette option sur un réseau public. Continuer ?"
            ),
            parent=self,
        ):
            return
        if self.companion:
            self.companion.stop()
        port = int(self.settings.get("companion", {}).get("port", 8765))
        self.companion = LocalCompanionServer(
            self.database,
            self.profiles_by_id,
            token=self._companion_token(),
        )
        try:
            url = self.companion.start(lan=lan, port=port)
        except OSError as exc:
            self.companion = None
            messagebox.showerror("Compagnon local", str(exc), parent=self)
            return
        self.settings.setdefault("companion", {})["lan"] = lan
        self.settings_repo.save(self.settings)
        scope = "réseau local" if lan else "ordinateur uniquement"
        self.companion_status.configure(text=f"Actif ({scope}) : {url}")

    def _stop_companion(self) -> None:
        if self.companion:
            self.companion.stop()
        self.companion = None
        self.companion_status.configure(text="Compagnon arrêté")

    def _open_companion(self) -> None:
        if not self.companion or not self.companion.running:
            messagebox.showwarning("Compagnon local", "Démarrez d'abord le compagnon.", parent=self)
            return
        webbrowser.open(self.companion.access_url)

    def _build_bulk_tab(self) -> None:
        tab = self._add_tab("🧰 Actions & annulation")
        tab.columnconfigure(0, weight=3)
        tab.columnconfigure(1, weight=2)
        tab.rowconfigure(0, weight=1)
        left = ttk.LabelFrame(tab, text=" Action groupée sécurisée ")
        right = ttk.LabelFrame(tab, text=" Historique d'annulation ")
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        self.bulk_tree = ttk.Treeview(
            left,
            columns=("nickname", "species", "location"),
            show="headings",
            selectmode="extended",
        )
        for key, title in (("nickname", "Surnom"), ("species", "Espèce"), ("location", "Emplacement")):
            self.bulk_tree.heading(key, text=title)
        self.bulk_tree.grid(row=0, column=0, columnspan=4, sticky="nsew", padx=6, pady=6)
        ttk.Label(left, text="Action").grid(row=1, column=0, padx=6, pady=6, sticky="w")
        self.bulk_action = ttk.Combobox(left, state="readonly", values=self.BULK_ACTIONS, width=20)
        self.bulk_action.set("observation")
        self.bulk_action.grid(row=1, column=1, padx=6, pady=6, sticky="w")
        ttk.Label(left, text="Note").grid(row=2, column=0, padx=6, pady=6, sticky="w")
        self.bulk_note = ttk.Entry(left)
        self.bulk_note.grid(row=2, column=1, columnspan=3, padx=6, pady=6, sticky="ew")
        ttk.Button(left, text="Prévisualiser", command=self._preview_bulk).grid(row=3, column=1, padx=6, pady=8)
        ttk.Button(
            left,
            text="Valider l'action groupée",
            command=self._apply_bulk,
            style="Accent.TButton",
        ).grid(row=3, column=2, padx=6, pady=8)
        self.history_tree = ttk.Treeview(
            right,
            columns=("date", "summary", "state"),
            show="headings",
            selectmode="browse",
        )
        for key, title, width in (
            ("date", "Date", 140),
            ("summary", "Action", 300),
            ("state", "État", 80),
        ):
            self.history_tree.heading(key, text=title)
            self.history_tree.column(key, width=width)
        self.history_tree.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        ttk.Button(right, text="Annuler l'action sélectionnée", command=self._undo_selected).grid(
            row=1, column=0, padx=6, pady=8, sticky="e"
        )

    def _selected_bulk_ids(self) -> list[str]:
        return list(self.bulk_tree.selection())

    def _preview_bulk(self) -> None:
        ids = self._selected_bulk_ids()
        if not ids:
            messagebox.showwarning("Action groupée", "Sélectionnez des plantes.", parent=self)
            return
        names = [next(plant["surnom"] for plant in self.plants if plant["id"] == identifier) for identifier in ids]
        messagebox.showinfo(
            "Prévisualisation",
            f"Action : {self.bulk_action.get()}\nPlantes : {len(ids)}\n\n" + "\n".join(f"• {name}" for name in names[:30]),
            parent=self,
        )

    def _apply_bulk(self) -> None:
        ids = self._selected_bulk_ids()
        action = self.bulk_action.get()
        if not ids:
            messagebox.showwarning("Action groupée", "Sélectionnez des plantes.", parent=self)
            return
        if not messagebox.askyesno(
            "Confirmer l'action groupée",
            f"Enregistrer « {action} » pour {len(ids)} plante(s) ?\nCette action pourra être annulée depuis l'historique.",
            parent=self,
        ):
            return
        try:
            self.repository.apply_bulk_care(ids, action, self.bulk_note.get())
        except Exception as exc:
            messagebox.showerror("Action groupée", str(exc), parent=self)
            return
        self.bulk_note.delete(0, tk.END)
        if self.on_collection_refresh:
            self.on_collection_refresh()
        self._refresh_history()
        messagebox.showinfo("Action groupée", "Action enregistrée.", parent=self)

    def _undo_selected(self) -> None:
        selection = self.history_tree.selection()
        if not selection:
            return
        if not messagebox.askyesno("Annuler", "Restaurer l'état antérieur pour cette action ?", parent=self):
            return
        try:
            summary = self.repository.undo(selection[0])
        except Exception as exc:
            messagebox.showerror("Annulation", str(exc), parent=self)
            return
        if self.on_collection_refresh:
            self.on_collection_refresh()
        self._refresh_history()
        messagebox.showinfo("Annulation", f"Action annulée : {summary}", parent=self)

    def _build_propagation_tab(self) -> None:
        tab = self._add_tab("🌱 Boutures")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        form = ttk.LabelFrame(tab, text=" Nouvelle bouture ou division ")
        form.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        for index in range(8):
            form.columnconfigure(index, weight=1 if index in {1, 3, 5} else 0)
        ttk.Label(form, text="Plante mère").grid(row=0, column=0, padx=5, pady=6)
        self.prop_parent = ttk.Combobox(form, state="readonly")
        self.prop_parent.grid(row=0, column=1, padx=5, pady=6, sticky="ew")
        ttk.Label(form, text="Nom").grid(row=0, column=2, padx=5, pady=6)
        self.prop_label = ttk.Entry(form)
        self.prop_label.grid(row=0, column=3, padx=5, pady=6, sticky="ew")
        ttk.Label(form, text="Méthode").grid(row=0, column=4, padx=5, pady=6)
        self.prop_method = ttk.Combobox(
            form,
            state="readonly",
            values=("bouture_eau", "bouture_substrat", "division", "rejet", "marcottage", "semis", "autre"),
        )
        self.prop_method.set("bouture_substrat")
        self.prop_method.grid(row=0, column=5, padx=5, pady=6, sticky="ew")
        ttk.Label(form, text="Date").grid(row=0, column=6, padx=5, pady=6)
        self.prop_date = ttk.Entry(form, width=12)
        self.prop_date.insert(0, format_date_fr(date.today()))
        self.prop_date.grid(row=0, column=7, padx=5, pady=6)
        ttk.Button(form, text="Créer", command=self._create_propagation, style="Accent.TButton").grid(
            row=1, column=7, padx=5, pady=6
        )
        self.propagation_tree = ttk.Treeview(
            tab,
            columns=("parent", "label", "method", "started", "status", "child"),
            show="headings",
            selectmode="browse",
        )
        for key, title in (
            ("parent", "Plante mère"),
            ("label", "Bouture"),
            ("method", "Méthode"),
            ("started", "Début"),
            ("status", "État"),
            ("child", "Plante fille"),
        ):
            self.propagation_tree.heading(key, text=title)
        self.propagation_tree.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        actions = ttk.Frame(tab)
        actions.grid(row=2, column=0, sticky="ew", padx=10, pady=(5, 10))
        ttk.Button(actions, text="Marquer enracinée", command=lambda: self._update_propagation("enracinee")).pack(side="left", padx=3)
        ttk.Button(actions, text="Marquer échec", command=lambda: self._update_propagation("echec")).pack(side="left", padx=3)
        ttk.Button(actions, text="Lier à une plante fille", command=self._link_child).pack(side="left", padx=3)

    def _create_propagation(self) -> None:
        parent = self.plant_by_label.get(self.prop_parent.get())
        if not parent:
            return
        try:
            self.repository.add_propagation(
                parent["id"],
                self.prop_label.get(),
                self.prop_method.get(),
                self.prop_date.get(),
            )
        except Exception as exc:
            messagebox.showerror("Bouture", str(exc), parent=self)
            return
        self.prop_label.delete(0, tk.END)
        self._refresh_propagations()

    def _update_propagation(self, status: str) -> None:
        selection = self.propagation_tree.selection()
        if not selection:
            return
        self.repository.update_propagation(
            selection[0],
            rooted_on=date.today() if status == "enracinee" else None,
            status=status,
        )
        self._refresh_propagations()

    def _link_child(self) -> None:
        selection = self.propagation_tree.selection()
        if not selection:
            return
        labels = sorted(self.plant_by_label)
        child_label = simpledialog.askstring(
            "Plante fille",
            "Copiez le libellé exact de la plante fille :\n\n" + "\n".join(labels[:40]),
            parent=self,
        )
        child = self.plant_by_label.get(child_label or "")
        if child:
            self.repository.update_propagation(
                selection[0],
                child_plant_id=child["id"],
                status="plante_etablie",
            )
            self._refresh_propagations()

    def _build_inventory_tab(self) -> None:
        tab = self._add_tab("📦 Stock")
        tab.columnconfigure(0, weight=2)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        self.inventory_tree = ttk.Treeview(
            tab,
            columns=("name", "category", "quantity", "unit", "threshold", "expiry"),
            show="headings",
            selectmode="browse",
        )
        for key, title in (
            ("name", "Produit"),
            ("category", "Catégorie"),
            ("quantity", "Quantité"),
            ("unit", "Unité"),
            ("threshold", "Seuil"),
            ("expiry", "Expiration"),
        ):
            self.inventory_tree.heading(key, text=title)
        self.inventory_tree.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        self.inventory_tree.bind("<<TreeviewSelect>>", self._load_inventory_item)
        form = ttk.LabelFrame(tab, text=" Produit ")
        form.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        form.columnconfigure(1, weight=1)
        self.inv_vars = {key: tk.StringVar() for key in ("name", "category", "unit", "quantity", "threshold", "expiry", "notes")}
        for row, (key, label) in enumerate(
            (
                ("name", "Nom"),
                ("category", "Catégorie"),
                ("unit", "Unité"),
                ("quantity", "Quantité"),
                ("threshold", "Seuil d'alerte"),
                ("expiry", "Expiration"),
                ("notes", "Notes"),
            )
        ):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=5)
            ttk.Entry(form, textvariable=self.inv_vars[key]).grid(row=row, column=1, sticky="ew", padx=6, pady=5)
        self.current_inventory_id: str | None = None
        ttk.Button(form, text="Nouveau", command=self._new_inventory_item).grid(row=7, column=0, padx=6, pady=8)
        ttk.Button(form, text="Enregistrer", command=self._save_inventory_item, style="Accent.TButton").grid(row=7, column=1, padx=6, pady=8)
        ttk.Button(form, text="Entrée de stock", command=lambda: self._adjust_stock(True)).grid(row=8, column=0, padx=6, pady=5)
        ttk.Button(form, text="Utilisation", command=lambda: self._adjust_stock(False)).grid(row=8, column=1, padx=6, pady=5)

    def _new_inventory_item(self) -> None:
        self.current_inventory_id = None
        for variable in self.inv_vars.values():
            variable.set("")
        self.inv_vars["quantity"].set("0")
        self.inv_vars["threshold"].set("0")

    def _load_inventory_item(self, _event=None) -> None:
        selection = self.inventory_tree.selection()
        if not selection:
            return
        self.current_inventory_id = selection[0]
        item = next((row for row in self.repository.list_inventory() if row["id"] == selection[0]), None)
        if not item:
            return
        values = {
            "name": item["name"],
            "category": item["category"],
            "unit": item["unit"],
            "quantity": item["quantity"],
            "threshold": item["reorder_level"],
            "expiry": item.get("expires_on") or "",
            "notes": item.get("notes") or "",
        }
        for key, value in values.items():
            self.inv_vars[key].set(str(value))

    def _save_inventory_item(self) -> None:
        try:
            self.current_inventory_id = self.repository.save_inventory_item(
                item_id=self.current_inventory_id,
                name=self.inv_vars["name"].get(),
                category=self.inv_vars["category"].get(),
                unit=self.inv_vars["unit"].get(),
                quantity=float(self.inv_vars["quantity"].get().replace(",", ".")),
                reorder_level=float(self.inv_vars["threshold"].get().replace(",", ".")),
                expires_on=self.inv_vars["expiry"].get() or None,
                notes=self.inv_vars["notes"].get(),
            )
        except Exception as exc:
            messagebox.showerror("Stock", str(exc), parent=self)
            return
        self._refresh_inventory()
        self._refresh_history()

    def _adjust_stock(self, positive: bool) -> None:
        if not self.current_inventory_id:
            return
        raw = simpledialog.askstring("Stock", "Quantité :", parent=self)
        if not raw:
            return
        reason = simpledialog.askstring("Stock", "Motif :", parent=self) or "Ajustement"
        try:
            delta = abs(float(raw.replace(",", "."))) * (1 if positive else -1)
            self.repository.adjust_inventory(self.current_inventory_id, delta, reason)
        except Exception as exc:
            messagebox.showerror("Stock", str(exc), parent=self)
            return
        self._refresh_inventory()
        self._refresh_history()

    def _build_treatments_tab(self) -> None:
        tab = self._add_tab("🩹 Traitements")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        form = ttk.LabelFrame(tab, text=" Nouveau protocole ")
        form.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        for col in range(10):
            form.columnconfigure(col, weight=1 if col in {1, 3, 5} else 0)
        self.treat_plant = ttk.Combobox(form, state="readonly")
        self.treat_title = ttk.Entry(form)
        self.treat_product = ttk.Combobox(form, state="readonly")
        self.treat_interval = ttk.Entry(form, width=8)
        self.treat_interval.insert(0, "7")
        self.treat_steps = ttk.Entry(form, width=8)
        self.treat_steps.insert(0, "3")
        self.treat_dose = ttk.Entry(form, width=8)
        for col, label, widget in (
            (0, "Plante", self.treat_plant),
            (2, "Titre", self.treat_title),
            (4, "Produit", self.treat_product),
            (6, "Intervalle j", self.treat_interval),
            (7, "Étapes", self.treat_steps),
            (8, "Dose", self.treat_dose),
        ):
            ttk.Label(form, text=label).grid(row=0, column=col, padx=4, pady=6)
            widget.grid(row=1, column=col, padx=4, pady=6, sticky="ew")
        ttk.Button(form, text="Créer", command=self._create_treatment, style="Accent.TButton").grid(row=1, column=9, padx=5, pady=6)
        body = ttk.Panedwindow(tab, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 10))
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=3)
        body.add(right, weight=2)
        self.protocol_tree = ttk.Treeview(
            left,
            columns=("plant", "title", "progress", "next", "status"),
            show="headings",
        )
        for key, title in (("plant", "Plante"), ("title", "Protocole"), ("progress", "Progression"), ("next", "Prochaine date"), ("status", "État")):
            self.protocol_tree.heading(key, text=title)
        self.protocol_tree.pack(fill="both", expand=True)
        self.protocol_tree.bind("<<TreeviewSelect>>", lambda _e: self._refresh_treatment_steps())
        self.step_tree = ttk.Treeview(
            right,
            columns=("number", "due", "status", "done"),
            show="headings",
        )
        for key, title in (("number", "Étape"), ("due", "Échéance"), ("status", "État"), ("done", "Réalisée")):
            self.step_tree.heading(key, text=title)
        self.step_tree.pack(fill="both", expand=True)
        ttk.Button(right, text="Valider l'étape", command=self._complete_treatment_step, style="Accent.TButton").pack(anchor="e", pady=6)

    def _create_treatment(self) -> None:
        plant = self.plant_by_label.get(self.treat_plant.get())
        if not plant:
            return
        inventory = {f"{item['name']} — {item['quantity']:g} {item['unit']}": item for item in self.repository.list_inventory()}
        product = inventory.get(self.treat_product.get())
        dose_raw = self.treat_dose.get().strip()
        try:
            self.repository.create_treatment_protocol(
                plant["id"],
                self.treat_title.get(),
                date.today(),
                interval_days=int(self.treat_interval.get()),
                total_steps=int(self.treat_steps.get()),
                product_item_id=product["id"] if product else None,
                dose=float(dose_raw.replace(",", ".")) if dose_raw else None,
                dose_unit=product["unit"] if product else None,
            )
        except Exception as exc:
            messagebox.showerror("Traitement", str(exc), parent=self)
            return
        self._refresh_treatments()
        self._refresh_history()

    def _refresh_treatment_steps(self) -> None:
        self.step_tree.delete(*self.step_tree.get_children())
        selection = self.protocol_tree.selection()
        if not selection:
            return
        for step in self.repository.list_treatment_steps(selection[0]):
            self.step_tree.insert(
                "",
                "end",
                iid=step["id"],
                values=(step["step_number"], step["due_on"], step["status"], step.get("completed_on") or ""),
            )

    def _complete_treatment_step(self) -> None:
        selection = self.step_tree.selection()
        if not selection:
            return
        note = simpledialog.askstring("Traitement", "Observation :", parent=self) or ""
        try:
            self.repository.complete_treatment_step(selection[0], notes=note)
        except Exception as exc:
            messagebox.showerror("Traitement", str(exc), parent=self)
            return
        if self.on_collection_refresh:
            self.on_collection_refresh()
        self._refresh_inventory()
        self._refresh_treatments()

    def _build_notifications_tab(self) -> None:
        tab = self._add_tab("🔔 Notifications")
        config = self.settings.setdefault("notifications", {})
        form = ttk.LabelFrame(tab, text=" Règles de notification ")
        form.pack(fill="x", padx=10, pady=10)
        form.columnconfigure(1, weight=1)
        self.notif_enabled = tk.BooleanVar(value=bool(config.get("enabled", True)))
        self.notif_group = tk.BooleanVar(value=bool(config.get("group_by_location", True)))
        self.notif_times = tk.StringVar(value=", ".join(config.get("times", [config.get("time", "09:00")])))
        self.notif_quiet_start = tk.StringVar(value=str(config.get("quiet_start", "22:00")))
        self.notif_quiet_end = tk.StringVar(value=str(config.get("quiet_end", "07:00")))
        self.notif_max = tk.StringVar(value=str(config.get("max_items", 8)))
        ttk.Checkbutton(form, text="Notifications activées", variable=self.notif_enabled).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=6)
        ttk.Checkbutton(form, text="Regrouper par emplacement", variable=self.notif_group).grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=6)
        for row, (label, variable) in enumerate(
            (
                ("Heures, séparées par des virgules", self.notif_times),
                ("Début des heures silencieuses", self.notif_quiet_start),
                ("Fin des heures silencieuses", self.notif_quiet_end),
                ("Nombre maximal d'éléments", self.notif_max),
            ),
            start=2,
        ):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=6)
            ttk.Entry(form, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=6)
        actions = ttk.Frame(tab)
        actions.pack(fill="x", padx=10, pady=5)
        ttk.Button(actions, text="Enregistrer", command=self._save_notification_settings, style="Accent.TButton").pack(side="left", padx=3)
        ttk.Button(actions, text="Installer les rappels Windows", command=self._install_notification_tasks).pack(side="left", padx=3)
        ttk.Button(actions, text="Afficher le résumé maintenant", command=self._show_notifications_now).pack(side="left", padx=3)
        ttk.Button(actions, text="Reporter toutes les alertes de 24 h", command=self._snooze_notifications).pack(side="left", padx=3)
        self.notif_preview = tk.Text(tab, height=16, wrap="word", state="disabled")
        self.notif_preview.pack(fill="both", expand=True, padx=10, pady=(5, 10))

    def _notification_times(self) -> list[str]:
        return [part.strip() for part in self.notif_times.get().replace(";", ",").split(",") if part.strip()]

    def _save_notification_settings(self) -> None:
        config = self.settings.setdefault("notifications", {})
        config.update(
            {
                "enabled": self.notif_enabled.get(),
                "group_by_location": self.notif_group.get(),
                "times": self._notification_times() or ["09:00"],
                "time": (self._notification_times() or ["09:00"])[0],
                "quiet_start": self.notif_quiet_start.get().strip(),
                "quiet_end": self.notif_quiet_end.get().strip(),
                "max_items": max(1, min(int(self.notif_max.get()), 30)),
            }
        )
        self.settings_repo.save(self.settings)
        messagebox.showinfo("Notifications", "Réglages enregistrés.", parent=self)

    def _install_notification_tasks(self) -> None:
        try:
            self._save_notification_settings()
            self.notifications.install_windows_tasks(self._notification_times())
        except Exception as exc:
            messagebox.showerror("Notifications", str(exc), parent=self)
            return
        messagebox.showinfo("Notifications", "Rappels Windows installés.", parent=self)

    def _show_notifications_now(self) -> None:
        items = self.notifications.due_items(self.database, self.profiles_by_id)
        title, body = self.notifications.digest(items, self.settings)
        self.notif_preview.configure(state="normal")
        self.notif_preview.delete("1.0", tk.END)
        self.notif_preview.insert("1.0", title + "\n\n" + (body or "Aucune alerte."))
        self.notif_preview.configure(state="disabled")
        if body:
            self.notifications.show(title, body)

    def _snooze_notifications(self) -> None:
        items = self.notifications.due_items(self.database, self.profiles_by_id)
        self.notifications.snooze(self.database, [item.key for item in items], hours=24)
        self._show_notifications_now()

    def _build_environment_tab(self) -> None:
        tab = self._add_tab("🌦️ Météo & capteurs")
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        weather = ttk.LabelFrame(tab, text=" Météo locale facultative ")
        sensors = ttk.LabelFrame(tab, text=" Capteurs environnementaux ")
        weather.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        sensors.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        weather.columnconfigure(1, weight=1)
        weather.rowconfigure(3, weight=1)
        self.weather_city = tk.StringVar(value=str(self.settings.get("weather", {}).get("location_name", "")))
        ttk.Label(weather, text="Ville ou code postal").grid(row=0, column=0, padx=6, pady=6)
        ttk.Entry(weather, textvariable=self.weather_city).grid(row=0, column=1, sticky="ew", padx=6, pady=6)
        ttk.Button(weather, text="Rechercher et afficher", command=self._fetch_weather).grid(row=0, column=2, padx=6, pady=6)
        ttk.Label(
            weather,
            text="La météo ajuste uniquement la priorité des contrôles extérieurs ; elle ne déclenche aucun soin.",
            wraplength=500,
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=6, pady=4)
        self.weather_output = tk.Text(weather, wrap="word", state="disabled")
        self.weather_output.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=6, pady=6)
        sensors.columnconfigure(0, weight=1)
        sensors.rowconfigure(1, weight=1)
        top = ttk.Frame(sensors)
        top.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        ttk.Button(top, text="Ajouter un capteur", command=self._add_sensor).pack(side="left", padx=3)
        ttk.Button(top, text="Ajouter une mesure", command=self._add_sensor_reading).pack(side="left", padx=3)
        ttk.Button(top, text="Importer CSV", command=self._import_sensor_csv).pack(side="left", padx=3)
        self.sensor_tree = ttk.Treeview(
            sensors,
            columns=("name", "kind", "value", "unit", "time", "plant"),
            show="headings",
            selectmode="browse",
        )
        for key, title in (("name", "Capteur"), ("kind", "Type"), ("value", "Valeur"), ("unit", "Unité"), ("time", "Date"), ("plant", "Plante")):
            self.sensor_tree.heading(key, text=title)
        self.sensor_tree.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)

    def _fetch_weather(self) -> None:
        query = self.weather_city.get().strip()
        if not query:
            return
        try:
            locations = self.weather.geocode(query, count=1)
            if not locations:
                raise ValueError("Lieu introuvable.")
            location = locations[0]
            days = self.weather.forecast(location.latitude, location.longitude, timezone=location.timezone)
        except Exception as exc:
            messagebox.showerror("Météo", str(exc), parent=self)
            return
        self.settings["weather"] = {
            "enabled": True,
            "location_name": location.label,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "timezone": location.timezone,
        }
        self.settings_repo.save(self.settings)
        lines = [location.label, ""]
        for item in days:
            lines.append(
                f"{item.day:%d/%m} · {item.temperature_min if item.temperature_min is not None else '—'} / "
                f"{item.temperature_max if item.temperature_max is not None else '—'} °C · "
                f"pluie {item.precipitation_sum if item.precipitation_sum is not None else '—'} mm · "
                f"rafales {item.wind_gusts_max if item.wind_gusts_max is not None else '—'} km/h"
            )
        advisories = outdoor_care_advisories(days)
        if advisories:
            lines.extend(["", "Points de vigilance :", *[f"• {item}" for item in advisories]])
        self.weather_output.configure(state="normal")
        self.weather_output.delete("1.0", tk.END)
        self.weather_output.insert("1.0", "\n".join(lines))
        self.weather_output.configure(state="disabled")

    def _add_sensor(self) -> None:
        name = simpledialog.askstring("Capteur", "Nom :", parent=self)
        if not name:
            return
        kind = simpledialog.askstring("Capteur", "Type (température, humidité, lumière...) :", parent=self) or "autre"
        unit = simpledialog.askstring("Capteur", "Unité :", parent=self) or ""
        result = self.repository.create_sensor_source(name, kind, unit)
        self._refresh_sensors()
        messagebox.showinfo(
            "Capteur",
            (
                "Capteur créé.\n\n"
                f"ID : {result['id']}\n"
                f"Jeton d'envoi : {result['token']}\n\n"
                "Conservez ce jeton : il permet uniquement d'envoyer des mesures pour ce capteur."
            ),
            parent=self,
        )

    def _add_sensor_reading(self) -> None:
        selection = self.sensor_tree.selection()
        if not selection:
            return
        raw = simpledialog.askstring("Mesure", "Valeur :", parent=self)
        if raw is None:
            return
        try:
            self.repository.add_sensor_reading(selection[0], float(raw.replace(",", ".")))
        except Exception as exc:
            messagebox.showerror("Mesure", str(exc), parent=self)
            return
        self._refresh_sensors()

    def _import_sensor_csv(self) -> None:
        source = filedialog.askopenfilename(
            title="Importer des mesures",
            filetypes=(("CSV", "*.csv"),),
            parent=self,
        )
        if not source:
            return
        service = SensorImportService(self.repository)
        try:
            inspection = service.inspect_csv(source)
            if not inspection["valid"]:
                raise ValueError("Colonnes manquantes : " + ", ".join(inspection["missing_columns"]))
            if not messagebox.askyesno(
                "Importer les mesures",
                f"{inspection['rows']} ligne(s) seront analysées. Continuer ?",
                parent=self,
            ):
                return
            result = service.import_csv(source)
        except Exception as exc:
            messagebox.showerror("Capteurs", str(exc), parent=self)
            return
        self._refresh_sensors()
        messagebox.showinfo(
            "Capteurs",
            f"{result['created']} mesure(s) importée(s), {result['errors']} erreur(s).",
            parent=self,
        )

    def _build_taxonomy_tab(self) -> None:
        tab = self._add_tab("🧬 Mise à jour botanique")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        controls = ttk.Frame(tab)
        controls.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        ttk.Label(
            controls,
            text="Les changements GBIF sont proposés comme révisions locales et ne modifient jamais silencieusement le catalogue.",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(controls, text="Vérifier 25 fiches", command=lambda: self._start_taxonomy_check(25)).pack(side="left", padx=3)
        ttk.Button(controls, text="Vérifier la fiche sélectionnée", command=lambda: self._start_taxonomy_check(1)).pack(side="left", padx=3)
        body = ttk.Panedwindow(tab, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=2)
        body.add(right, weight=3)
        self.tax_profile_tree = ttk.Treeview(
            left,
            columns=("name", "family"),
            show="headings",
            selectmode="browse",
        )
        self.tax_profile_tree.heading("name", text="Nom actuel")
        self.tax_profile_tree.heading("family", text="Famille")
        self.tax_profile_tree.pack(fill="both", expand=True)
        self.tax_proposal_tree = ttk.Treeview(
            right,
            columns=("current", "proposed", "family", "confidence", "status"),
            show="headings",
            selectmode="browse",
        )
        for key, title in (("current", "Nom actuel"), ("proposed", "Nom proposé"), ("family", "Famille proposée"), ("confidence", "Confiance"), ("status", "État")):
            self.tax_proposal_tree.heading(key, text=title)
        self.tax_proposal_tree.pack(fill="both", expand=True)
        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=6)
        ttk.Button(actions, text="Appliquer comme révision locale", command=self._apply_taxonomy_proposal, style="Accent.TButton").pack(side="left", padx=3)
        ttk.Button(actions, text="Rejeter", command=self._reject_taxonomy_proposal).pack(side="left", padx=3)
        self.tax_status = ttk.Label(actions, text="")
        self.tax_status.pack(side="right")

    def _start_taxonomy_check(self, count: int) -> None:
        selection = self.tax_profile_tree.selection()
        if count == 1 and selection:
            identifiers = set(selection)
            profiles = [profile for profile in self.profiles_by_id.values() if str(profile.get("id")) in identifiers]
        else:
            profiles = list(self.profiles_by_id.values())[:count]
        if not profiles:
            return
        self.tax_status.configure(text=f"Vérification de {len(profiles)} fiche(s)…")

        def work() -> None:
            proposals = []
            errors = 0
            for profile in profiles:
                try:
                    proposal = self.taxonomy.check_profile(profile)
                    if proposal:
                        proposals.append(proposal)
                except Exception:
                    errors += 1
            self.after(0, lambda: self._taxonomy_check_done(len(proposals), errors))

        threading.Thread(target=work, daemon=True).start()

    def _taxonomy_check_done(self, proposals: int, errors: int) -> None:
        self.tax_status.configure(text=f"{proposals} proposition(s), {errors} erreur(s)")
        self._refresh_taxonomy_proposals()

    def _apply_taxonomy_proposal(self) -> None:
        selection = self.tax_proposal_tree.selection()
        if not selection:
            return
        proposal = next((item for item in self.repository.list_taxonomy_proposals() if item["id"] == selection[0]), None)
        if not proposal:
            return
        profile = self.profiles_by_id.get(proposal["species_id"])
        if not profile:
            messagebox.showerror("Taxonomie", "Fiche locale introuvable.", parent=self)
            return
        if not messagebox.askyesno(
            "Révision taxonomique",
            (
                f"Appliquer localement :\n{proposal['current_name']}\n→ {proposal['proposed_name']}\n"
                f"Famille : {proposal['proposed_family']}\n\nLe changement restera marqué « à vérifier »."
            ),
            parent=self,
        ):
            return
        try:
            self.taxonomy.apply_as_local_override(selection[0], profile)
        except Exception as exc:
            messagebox.showerror("Taxonomie", str(exc), parent=self)
            return
        if self.reload_catalogue:
            self.reload_catalogue()
        self._refresh_taxonomy_proposals()
        self._refresh_history()

    def _reject_taxonomy_proposal(self) -> None:
        selection = self.tax_proposal_tree.selection()
        if selection:
            self.taxonomy.reject(selection[0])
            self._refresh_taxonomy_proposals()

    def refresh(self) -> None:
        self.plants = self.database.load_plants()
        self.plant_by_label = {self._plant_label(plant): plant for plant in self.plants}
        labels = sorted(self.plant_by_label, key=str.casefold)
        self.prop_parent["values"] = labels
        self.treat_plant["values"] = labels
        if labels and not self.prop_parent.get():
            self.prop_parent.set(labels[0])
        if labels and not self.treat_plant.get():
            self.treat_plant.set(labels[0])
        self._refresh_plant_trees()
        self._refresh_history()
        self._refresh_propagations()
        self._refresh_inventory()
        self._refresh_treatments()
        self._refresh_sensors()
        self._refresh_taxonomy_profiles()
        self._refresh_taxonomy_proposals()

    def _refresh_plant_trees(self) -> None:
        for tree in (self.label_tree, self.bulk_tree):
            tree.delete(*tree.get_children())
            for plant in self.plants:
                profile = self.profiles_by_id.get(plant["species_id"], {})
                context = plant.get("contexte") if isinstance(plant.get("contexte"), dict) else {}
                tree.insert(
                    "",
                    "end",
                    iid=plant["id"],
                    values=(
                        plant["surnom"],
                        scientific_name(profile) if profile else plant["species_id"],
                        context.get("emplacement", ""),
                    ),
                )

    def _refresh_history(self) -> None:
        self.history_tree.delete(*self.history_tree.get_children())
        for item in self.repository.list_history():
            self.history_tree.insert(
                "",
                "end",
                iid=item["id"],
                values=(item["created_at"], item["summary"], "annulée" if item["undone_at"] else "active"),
            )

    def _refresh_propagations(self) -> None:
        self.propagation_tree.delete(*self.propagation_tree.get_children())
        for item in self.repository.list_propagations():
            self.propagation_tree.insert(
                "",
                "end",
                iid=item["id"],
                values=(
                    item["parent_nickname"],
                    item["label"],
                    item["method"],
                    item["started_on"],
                    item["status"],
                    item.get("child_nickname") or "",
                ),
            )

    def _refresh_inventory(self) -> None:
        self.inventory_tree.delete(*self.inventory_tree.get_children())
        inventory = self.repository.list_inventory()
        for item in inventory:
            self.inventory_tree.insert(
                "",
                "end",
                iid=item["id"],
                values=(
                    ("⚠ " if item["low_stock"] else "") + item["name"],
                    item["category"],
                    f"{item['quantity']:g}",
                    item["unit"],
                    f"{item['reorder_level']:g}",
                    item.get("expires_on") or "",
                ),
            )
        product_values = [f"{item['name']} — {item['quantity']:g} {item['unit']}" for item in inventory]
        self.treat_product["values"] = ("— Aucun produit —", *product_values)
        if not self.treat_product.get():
            self.treat_product.set("— Aucun produit —")

    def _refresh_treatments(self) -> None:
        self.protocol_tree.delete(*self.protocol_tree.get_children())
        for item in self.repository.list_treatment_protocols():
            self.protocol_tree.insert(
                "",
                "end",
                iid=item["id"],
                values=(
                    item["nickname"],
                    item["title"],
                    f"{item['completed_steps']}/{item['total_steps']}",
                    item.get("next_due") or "",
                    item["status"],
                ),
            )
        self._refresh_treatment_steps()

    def _refresh_sensors(self) -> None:
        self.sensor_tree.delete(*self.sensor_tree.get_children())
        for item in self.repository.latest_sensor_readings():
            self.sensor_tree.insert(
                "",
                "end",
                iid=item["source_id"],
                values=(
                    item["name"],
                    item["kind"],
                    item.get("value") if item.get("value") is not None else "—",
                    item.get("unit") or item.get("configured_unit") or "",
                    item.get("recorded_at") or "",
                    item.get("nickname") or "",
                ),
            )

    def _refresh_taxonomy_profiles(self) -> None:
        self.tax_profile_tree.delete(*self.tax_profile_tree.get_children())
        for profile in list(self.profiles_by_id.values())[:500]:
            tax = profile.get("taxonomie") if isinstance(profile.get("taxonomie"), dict) else {}
            identifier = str(profile.get("id") or "")
            if identifier:
                self.tax_profile_tree.insert(
                    "",
                    "end",
                    iid=identifier,
                    values=(scientific_name(profile), tax.get("famille", "")),
                )

    def _refresh_taxonomy_proposals(self) -> None:
        self.tax_proposal_tree.delete(*self.tax_proposal_tree.get_children())
        for item in self.repository.list_taxonomy_proposals():
            self.tax_proposal_tree.insert(
                "",
                "end",
                iid=item["id"],
                values=(
                    item["current_name"],
                    item["proposed_name"],
                    item["proposed_family"],
                    item.get("confidence") if item.get("confidence") is not None else "—",
                    item["status"],
                ),
            )
