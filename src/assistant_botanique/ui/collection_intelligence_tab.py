"""Atelier collection : emplacements, infestations, rempotage, règles et outils locaux."""
from __future__ import annotations

import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable, Mapping

from core import scientific_name
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.infrastructure.intelligence_repository import IntelligenceRepository
from assistant_botanique.infrastructure.settings import SettingsRepository
from assistant_botanique.services.accessibility import AccessibilityManager, normalized_accessibility
from assistant_botanique.services.backup import BackupService
from assistant_botanique.services.encrypted_sync import EncryptedSyncService
from assistant_botanique.services.photo_compare import PhotoCompareService
from assistant_botanique.services.photos import PhotoService
from assistant_botanique.services.plugin_manager import PluginManager
from assistant_botanique.services.repotting import recommend_repotting
from assistant_botanique.services.rules_engine import RulesEngine


class CollectionIntelligenceTab(ttk.Frame):
    def __init__(
        self,
        parent,
        root: tk.Misc,
        database: Database,
        profiles_by_id: Mapping[str, Mapping[str, Any]],
        settings: dict[str, Any],
        settings_repo: SettingsRepository,
        *,
        on_collection_refresh: Callable[[], None] | None = None,
        on_accessibility_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.root_window = root
        self.database = database
        self.profiles_by_id = profiles_by_id
        self.settings = settings
        self.settings_repo = settings_repo
        self.on_collection_refresh = on_collection_refresh
        self.on_accessibility_changed = on_accessibility_changed
        self.repository = IntelligenceRepository(database)
        self.rules = RulesEngine(database)
        self.photos = PhotoService(database)
        self.photo_compare = PhotoCompareService(self.photos)
        self.sync = EncryptedSyncService(BackupService(database))
        self.plugins = PluginManager(self.repository)
        self.plants: list[dict[str, Any]] = []
        self.plant_by_label: dict[str, dict[str, Any]] = {}
        self.location_by_label: dict[str, dict[str, Any]] = {}
        self.case_rows: dict[str, dict[str, Any]] = {}
        self.photo_rows: dict[str, dict[str, Any]] = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(header, text="Collection & analyse", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(
            header,
            text="Outils avancés locaux. Les règles créent uniquement des alertes ou tâches vérifiables.",
        ).pack(side="left", padx=14)
        ttk.Button(header, text="Actualiser", command=self.refresh).pack(side="right")
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self._build_locations()
        self._build_infestations()
        self._build_repotting()
        self._build_rules()
        self._build_photos()
        self._build_sync()
        self._build_accessibility()
        self._build_plugins()

    def _tab(self, title: str) -> ttk.Frame:
        frame = ttk.Frame(self.tabs)
        self.tabs.add(frame, text=title)
        return frame

    def _plant_label(self, plant: Mapping[str, Any]) -> str:
        profile = self.profiles_by_id.get(str(plant.get("species_id") or ""), {})
        species = scientific_name(profile) if profile else str(plant.get("species_id") or "")
        return f"{plant.get('surnom', 'Sans nom')} — {species}"

    def _selected_plant(self, combo: ttk.Combobox) -> dict[str, Any] | None:
        return self.plant_by_label.get(combo.get())

    # --- Plan des emplacements --------------------------------------
    def _build_locations(self) -> None:
        tab = self._tab("🗺️ Emplacements")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self.location_tree = ttk.Treeview(tab, columns=("path", "kind", "plants"), show="headings")
        for key, title, width in (("path", "Chemin", 440), ("kind", "Type", 120), ("plants", "Plantes", 80)):
            self.location_tree.heading(key, text=title)
            self.location_tree.column(key, width=width, anchor="w")
        self.location_tree.grid(row=0, column=0, columnspan=5, sticky="nsew", padx=10, pady=8)
        ttk.Button(tab, text="Ajouter une zone", command=self._add_location).grid(row=1, column=0, padx=5, pady=6)
        ttk.Button(tab, text="Ajouter une sous-zone", command=lambda: self._add_location(child=True)).grid(row=1, column=1, padx=5, pady=6)
        ttk.Button(tab, text="Supprimer", command=self._delete_location).grid(row=1, column=2, padx=5, pady=6)
        assign = ttk.LabelFrame(tab, text=" Positionner une plante ")
        assign.grid(row=2, column=0, columnspan=5, sticky="ew", padx=10, pady=8)
        assign.columnconfigure(1, weight=1)
        assign.columnconfigure(3, weight=1)
        ttk.Label(assign, text="Plante").grid(row=0, column=0, padx=6, pady=6)
        self.location_plant = ttk.Combobox(assign, state="readonly")
        self.location_plant.grid(row=0, column=1, padx=6, pady=6, sticky="ew")
        ttk.Label(assign, text="Emplacement").grid(row=0, column=2, padx=6, pady=6)
        self.location_choice = ttk.Combobox(assign, state="readonly")
        self.location_choice.grid(row=0, column=3, padx=6, pady=6, sticky="ew")
        ttk.Button(assign, text="Affecter", command=self._assign_location, style="Accent.TButton").grid(row=0, column=4, padx=6, pady=6)

    def _add_location(self, child: bool = False) -> None:
        parent_id = None
        if child:
            selection = self.location_tree.selection()
            if not selection:
                messagebox.showwarning("Emplacements", "Sélectionnez l'emplacement parent.", parent=self)
                return
            parent_id = selection[0]
        name = simpledialog.askstring("Nouvel emplacement", "Nom de la zone :", parent=self)
        if not name:
            return
        kind = simpledialog.askstring("Type", "Type : pièce, fenêtre, étagère, serre, jardin…", initialvalue="zone", parent=self) or "zone"
        try:
            self.repository.add_location(name, parent_id=parent_id, kind=kind)
        except Exception as exc:
            messagebox.showerror("Emplacements", str(exc), parent=self)
            return
        self._refresh_locations()

    def _delete_location(self) -> None:
        selection = self.location_tree.selection()
        if not selection:
            return
        if not messagebox.askyesno("Supprimer", "Supprimer cet emplacement vide ?", parent=self):
            return
        try:
            self.repository.delete_location(selection[0])
        except Exception as exc:
            messagebox.showerror("Emplacements", str(exc), parent=self)
            return
        self._refresh_locations()

    def _assign_location(self) -> None:
        plant = self._selected_plant(self.location_plant)
        location = self.location_by_label.get(self.location_choice.get())
        if not plant or not location:
            messagebox.showwarning("Emplacements", "Sélectionnez une plante et un emplacement.", parent=self)
            return
        try:
            self.repository.assign_plant_location(plant["id"], location["id"])
        except Exception as exc:
            messagebox.showerror("Emplacements", str(exc), parent=self)
            return
        if self.on_collection_refresh:
            self.on_collection_refresh()
        self._refresh_locations()

    def _refresh_locations(self) -> None:
        locations = self.repository.list_locations()
        self.location_tree.delete(*self.location_tree.get_children())
        for item in locations:
            self.location_tree.insert("", "end", iid=item["id"], values=(item["path"], item["kind"], item["plant_count"]))
        self.location_by_label = {item["path"]: item for item in locations}
        self.location_choice["values"] = tuple(self.location_by_label)
        if self.location_by_label and self.location_choice.get() not in self.location_by_label:
            self.location_choice.set(next(iter(self.location_by_label)))

    # --- Infestations ------------------------------------------------
    def _build_infestations(self) -> None:
        tab = self._tab("🐛 Infestations")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self.infestation_tree = ttk.Treeview(tab, columns=("title", "pest", "status", "severity", "plants"), show="headings")
        for key, title, width in (
            ("title", "Incident", 240), ("pest", "Ravageur", 180), ("status", "État", 100),
            ("severity", "Gravité", 80), ("plants", "Plantes", 80),
        ):
            self.infestation_tree.heading(key, text=title)
            self.infestation_tree.column(key, width=width)
        self.infestation_tree.grid(row=0, column=0, columnspan=5, sticky="nsew", padx=10, pady=8)
        ttk.Button(tab, text="Nouvel incident", command=self._new_infestation, style="Accent.TButton").grid(row=1, column=0, padx=5, pady=6)
        ttk.Button(tab, text="Ajouter une plante", command=self._add_infestation_plant).grid(row=1, column=1, padx=5, pady=6)
        ttk.Button(tab, text="Ajouter une observation", command=self._observe_infestation).grid(row=1, column=2, padx=5, pady=6)
        ttk.Button(tab, text="Clôturer", command=self._resolve_infestation).grid(row=1, column=3, padx=5, pady=6)
        self.infestation_details = tk.Text(tab, height=9, wrap="word", state="disabled")
        self.infestation_details.grid(row=2, column=0, columnspan=5, sticky="ew", padx=10, pady=8)
        self.infestation_tree.bind("<<TreeviewSelect>>", lambda _event: self._show_infestation())

    def _case(self) -> dict[str, Any] | None:
        selection = self.infestation_tree.selection()
        return self.case_rows.get(selection[0]) if selection else None

    def _new_infestation(self) -> None:
        title = simpledialog.askstring("Incident", "Nom de l'incident :", parent=self)
        if not title:
            return
        pest = simpledialog.askstring("Ravageur", "Ravageur ou symptôme suspecté :", parent=self)
        if not pest:
            return
        severity = simpledialog.askinteger("Gravité", "Gravité de 1 à 5 :", initialvalue=2, minvalue=1, maxvalue=5, parent=self) or 2
        self.repository.create_infestation(title, pest, tk_today(), severity=severity)
        self._refresh_infestations()

    def _add_infestation_plant(self) -> None:
        case = self._case()
        if not case:
            messagebox.showwarning("Infestation", "Sélectionnez un incident.", parent=self)
            return
        label = simpledialog.askstring("Plante", "Saisissez exactement le début du surnom ou choisissez-le ensuite :", parent=self)
        plant = next((item for item in self.plants if str(item["surnom"]).casefold().startswith(str(label or "").casefold())), None)
        if not plant:
            messagebox.showwarning("Infestation", "Plante introuvable. Utilisez son surnom.", parent=self)
            return
        exposed = messagebox.askyesno("Rôle", "Cette plante est-elle seulement exposée, sans symptôme confirmé ?", parent=self)
        self.repository.add_plant_to_infestation(case["id"], plant["id"], role="exposee" if exposed else "atteinte")
        self._refresh_infestations()

    def _observe_infestation(self) -> None:
        case = self._case()
        if not case:
            return
        note = simpledialog.askstring("Observation", "Évolution, comptage, zone touchée ou résultat du contrôle :", parent=self)
        if not note:
            return
        severity = simpledialog.askinteger("Gravité", "Gravité actuelle de 1 à 5 :", initialvalue=case.get("severity", 2), minvalue=1, maxvalue=5, parent=self) or 2
        self.repository.add_infestation_observation(case["id"], note, severity=severity)
        self._refresh_infestations()

    def _resolve_infestation(self) -> None:
        case = self._case()
        if case and messagebox.askyesno("Clôturer", "Clôturer cet incident ?", parent=self):
            self.repository.resolve_infestation(case["id"])
            self._refresh_infestations()

    def _show_infestation(self) -> None:
        case = self._case()
        lines = []
        if case:
            lines = [f"{case['title']} — {case['pest']}", f"Détecté le {case['detected_on']} · état {case['status']}", "", "Plantes :"]
            lines.extend(f"• {item['nickname']} — {item['role']} — {item['status']}" for item in case["plants"])
            lines.append("\nObservations :")
            lines.extend(f"• {item['observed_on']} — niveau {item['severity']} — {item['notes']}" for item in case["observations"][:20])
        self.infestation_details.configure(state="normal")
        self.infestation_details.delete("1.0", tk.END)
        self.infestation_details.insert("1.0", "\n".join(lines))
        self.infestation_details.configure(state="disabled")

    def _refresh_infestations(self) -> None:
        cases = self.repository.list_infestations()
        self.case_rows = {item["id"]: item for item in cases}
        self.infestation_tree.delete(*self.infestation_tree.get_children())
        for item in cases:
            self.infestation_tree.insert("", "end", iid=item["id"], values=(item["title"], item["pest"], item["status"], item["severity"], item["plant_count"]))
        self._show_infestation()

    # --- Rempotage ---------------------------------------------------
    def _build_repotting(self) -> None:
        tab = self._tab("🪴 Rempotage")
        form = ttk.LabelFrame(tab, text=" Évaluation ")
        form.pack(fill="x", padx=10, pady=10)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Plante").grid(row=0, column=0, padx=6, pady=6)
        self.repot_plant = ttk.Combobox(form, state="readonly")
        self.repot_plant.grid(row=0, column=1, columnspan=3, padx=6, pady=6, sticky="ew")
        self.repot_crowded = tk.BooleanVar()
        self.repot_damaged = tk.BooleanVar()
        self.repot_unstable = tk.BooleanVar()
        ttk.Checkbutton(form, text="Racines serrées", variable=self.repot_crowded).grid(row=1, column=0, padx=6, pady=6)
        ttk.Checkbutton(form, text="Racines abîmées", variable=self.repot_damaged).grid(row=1, column=1, padx=6, pady=6)
        ttk.Checkbutton(form, text="Plante instable", variable=self.repot_unstable).grid(row=1, column=2, padx=6, pady=6)
        ttk.Label(form, text="Croissance").grid(row=2, column=0, padx=6, pady=6)
        self.repot_growth = ttk.Combobox(form, state="readonly", values=("normale", "vigoureuse", "ralentie"), width=15)
        self.repot_growth.set("normale")
        self.repot_growth.grid(row=2, column=1, padx=6, pady=6, sticky="w")
        ttk.Label(form, text="Âge du substrat (mois)").grid(row=2, column=2, padx=6, pady=6)
        self.repot_age = ttk.Entry(form, width=8)
        self.repot_age.insert(0, "12")
        self.repot_age.grid(row=2, column=3, padx=6, pady=6, sticky="w")
        ttk.Button(form, text="Calculer", command=self._calculate_repotting, style="Accent.TButton").grid(row=3, column=3, padx=6, pady=8)
        self.repot_output = tk.Text(tab, wrap="word", state="disabled")
        self.repot_output.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _calculate_repotting(self) -> None:
        plant = self._selected_plant(self.repot_plant)
        if not plant:
            return
        profile = self.profiles_by_id.get(plant["species_id"], {})
        try:
            age = int(self.repot_age.get() or 0)
            result = recommend_repotting(
                plant, profile,
                roots_crowded=self.repot_crowded.get(), roots_damaged=self.repot_damaged.get(),
                unstable=self.repot_unstable.get(), growth_state=self.repot_growth.get(),
                substrate_age_months=age,
            )
        except Exception as exc:
            messagebox.showerror("Rempotage", str(exc), parent=self)
            return
        lines = [
            f"Priorité : {result.urgency}",
            f"Pot actuel : {result.current_volume_l:g} L",
            f"Volume proposé : environ {result.target_volume_l:g} L",
            "", "Raisons :", *(f"• {item}" for item in result.reasons),
            "", "Mélange indicatif :", *(f"• {name} : {volume:g} L" for name, volume in result.mix_liters),
            "", "Précautions :", *(f"• {item}" for item in result.cautions),
        ]
        self.repot_output.configure(state="normal")
        self.repot_output.delete("1.0", tk.END)
        self.repot_output.insert("1.0", "\n".join(lines))
        self.repot_output.configure(state="disabled")

    # --- Règles ------------------------------------------------------
    def _build_rules(self) -> None:
        tab = self._tab("⚙️ Règles")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self.rule_tree = ttk.Treeview(tab, columns=("name", "condition", "action", "enabled", "last"), show="headings")
        for key, title, width in (("name", "Nom", 220), ("condition", "Condition", 230), ("action", "Action", 180), ("enabled", "Active", 70), ("last", "Dernier déclenchement", 160)):
            self.rule_tree.heading(key, text=title)
            self.rule_tree.column(key, width=width)
        self.rule_tree.grid(row=0, column=0, columnspan=5, sticky="nsew", padx=10, pady=8)
        ttk.Button(tab, text="Nouvelle règle", command=self._new_rule, style="Accent.TButton").grid(row=1, column=0, padx=5, pady=6)
        ttk.Button(tab, text="Activer / désactiver", command=self._toggle_rule).grid(row=1, column=1, padx=5, pady=6)
        ttk.Button(tab, text="Évaluer maintenant", command=self._evaluate_rules).grid(row=1, column=2, padx=5, pady=6)
        ttk.Button(tab, text="Acquitter les alertes", command=self._ack_alerts).grid(row=1, column=3, padx=5, pady=6)
        self.rule_alerts = tk.Text(tab, height=8, wrap="word", state="disabled")
        self.rule_alerts.grid(row=2, column=0, columnspan=5, sticky="ew", padx=10, pady=8)

    def _new_rule(self) -> None:
        name = simpledialog.askstring("Règle", "Nom de la règle :", parent=self)
        if not name:
            return
        condition_type = simpledialog.askstring(
            "Condition",
            "Type : days_since_watering_gte, active_infestation, location, sensor_below ou sensor_above",
            initialvalue="days_since_watering_gte",
            parent=self,
        ) or ""
        condition: dict[str, Any] = {"type": condition_type}
        if condition_type == "days_since_watering_gte":
            condition["days"] = simpledialog.askinteger("Jours", "Nombre de jours :", initialvalue=14, minvalue=0, parent=self) or 0
        elif condition_type == "location":
            location = self.location_by_label.get(simpledialog.askstring("Emplacement", "Chemin exact de l'emplacement :", parent=self) or "")
            if not location:
                messagebox.showerror("Règle", "Emplacement introuvable.", parent=self)
                return
            condition["location_id"] = location["id"]
        elif condition_type in {"sensor_below", "sensor_above"}:
            condition["source_id"] = simpledialog.askstring("Capteur", "Identifiant du capteur :", parent=self) or ""
            condition["value"] = simpledialog.askfloat("Seuil", "Valeur seuil :", parent=self) or 0
        action_type = simpledialog.askstring("Action", "Action : create_alert ou create_task", initialvalue="create_alert", parent=self) or ""
        message = simpledialog.askstring("Message", "Message ({plant} sera remplacé par le surnom) :", initialvalue="Contrôler {plant}", parent=self) or "Contrôler {plant}"
        action: dict[str, Any] = {"type": action_type, "message": message}
        if action_type == "create_task":
            action["care_type"] = simpledialog.askstring("Soin", "Type de soin :", initialvalue="observation", parent=self) or "observation"
            action["due_in_days"] = simpledialog.askinteger("Échéance", "Échéance dans combien de jours ?", initialvalue=0, minvalue=0, parent=self) or 0
        try:
            self.rules.validate_rule(condition, action)
            self.repository.save_rule(rule_id=None, name=name, condition=condition, action=action)
        except Exception as exc:
            messagebox.showerror("Règle", str(exc), parent=self)
            return
        self._refresh_rules()

    def _toggle_rule(self) -> None:
        selection = self.rule_tree.selection()
        if not selection:
            return
        rule = next((item for item in self.repository.list_rules() if item["id"] == selection[0]), None)
        if rule:
            self.repository.set_rule_enabled(rule["id"], not bool(rule["enabled"]))
            self._refresh_rules()

    def _evaluate_rules(self) -> None:
        try:
            results = self.rules.evaluate_all()
        except Exception as exc:
            messagebox.showerror("Règles", str(exc), parent=self)
            return
        messagebox.showinfo("Règles", "\n".join(f"• {item.rule_name} : {item.message}" for item in results) or "Aucune règle active.", parent=self)
        self._refresh_rules()

    def _ack_alerts(self) -> None:
        for item in self.repository.list_rule_alerts():
            self.repository.acknowledge_alert(item["id"])
        self._refresh_rules()

    def _refresh_rules(self) -> None:
        rules = self.repository.list_rules()
        self.rule_tree.delete(*self.rule_tree.get_children())
        for item in rules:
            self.rule_tree.insert("", "end", iid=item["id"], values=(item["name"], str(item["condition"]), str(item["action"]), "Oui" if item["enabled"] else "Non", item.get("last_triggered_at") or "—"))
        alerts = self.repository.list_rule_alerts()
        self.rule_alerts.configure(state="normal")
        self.rule_alerts.delete("1.0", tk.END)
        self.rule_alerts.insert("1.0", "\n".join(f"• {item['rule_name']} — {item.get('nickname') or 'Collection'} : {item['message']}" for item in alerts) or "Aucune alerte ouverte.")
        self.rule_alerts.configure(state="disabled")

    # --- Photos ------------------------------------------------------
    def _build_photos(self) -> None:
        tab = self._tab("🖼️ Comparateur")
        form = ttk.LabelFrame(tab, text=" Comparer deux photos d'une plante ")
        form.pack(fill="x", padx=10, pady=10)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Plante").grid(row=0, column=0, padx=6, pady=6)
        self.compare_plant = ttk.Combobox(form, state="readonly")
        self.compare_plant.grid(row=0, column=1, columnspan=3, padx=6, pady=6, sticky="ew")
        self.compare_plant.bind("<<ComboboxSelected>>", lambda _event: self._refresh_photo_choices())
        ttk.Label(form, text="Première photo").grid(row=1, column=0, padx=6, pady=6)
        self.compare_first = ttk.Combobox(form, state="readonly")
        self.compare_first.grid(row=1, column=1, padx=6, pady=6, sticky="ew")
        ttk.Label(form, text="Deuxième photo").grid(row=2, column=0, padx=6, pady=6)
        self.compare_second = ttk.Combobox(form, state="readonly")
        self.compare_second.grid(row=2, column=1, padx=6, pady=6, sticky="ew")
        ttk.Button(form, text="Ouvrir la comparaison", command=self._compare_photos, style="Accent.TButton").grid(row=3, column=1, padx=6, pady=8, sticky="w")
        ttk.Label(
            tab,
            text="Le curseur superpose les deux images ; une vue côte à côte est également générée. Les fichiers restent locaux.",
            wraplength=900,
        ).pack(anchor="w", padx=14, pady=6)

    def _refresh_photo_choices(self) -> None:
        plant = self._selected_plant(self.compare_plant)
        photos = self.database.list_photos(plant["id"] if plant else None) if plant else []
        labels = []
        self.photo_rows = {}
        for index, item in enumerate(photos):
            label = f"{item.get('taken_at', 'date inconnue')} — {item.get('caption') or 'sans légende'} — {index + 1}"
            labels.append(label)
            self.photo_rows[label] = item
        self.compare_first["values"] = labels
        self.compare_second["values"] = labels
        if labels:
            self.compare_first.set(labels[-1])
            self.compare_second.set(labels[0])

    def _compare_photos(self) -> None:
        first = self.photo_rows.get(self.compare_first.get())
        second = self.photo_rows.get(self.compare_second.get())
        if not first or not second or first["id"] == second["id"]:
            messagebox.showwarning("Photos", "Sélectionnez deux photos différentes.", parent=self)
            return
        destination = filedialog.asksaveasfilename(title="Enregistrer la comparaison", defaultextension=".html", filetypes=(("Page HTML", "*.html"),), parent=self)
        if not destination:
            return
        try:
            output = self.photo_compare.generate_html(first, second, destination, title=self.compare_plant.get())
        except Exception as exc:
            messagebox.showerror("Photos", str(exc), parent=self)
            return
        webbrowser.open(output.as_uri())

    # --- Synchronisation --------------------------------------------
    def _build_sync(self) -> None:
        tab = self._tab("🔐 Synchronisation")
        frame = ttk.LabelFrame(tab, text=" Snapshots chiffrés dans un dossier synchronisé ")
        frame.pack(fill="x", padx=10, pady=10)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Dossier").grid(row=0, column=0, padx=6, pady=6)
        self.sync_folder = ttk.Entry(frame)
        self.sync_folder.grid(row=0, column=1, padx=6, pady=6, sticky="ew")
        self.sync_folder.insert(0, str(self.settings.get("sync", {}).get("folder") or ""))
        ttk.Button(frame, text="Choisir", command=self._choose_sync_folder).grid(row=0, column=2, padx=6, pady=6)
        ttk.Button(frame, text="Envoyer un snapshot", command=self._push_sync, style="Accent.TButton").grid(row=1, column=0, padx=6, pady=8)
        ttk.Button(frame, text="Restaurer le plus récent", command=self._pull_sync).grid(row=1, column=1, padx=6, pady=8, sticky="w")
        ttk.Button(frame, text="État", command=self._sync_status).grid(row=1, column=2, padx=6, pady=8)
        self.sync_status = ttk.Label(tab, text="Le mot de passe n'est jamais enregistré.", wraplength=950)
        self.sync_status.pack(fill="x", padx=14, pady=8)

    def _choose_sync_folder(self) -> None:
        value = filedialog.askdirectory(title="Choisir le dossier de synchronisation", parent=self)
        if value:
            self.sync_folder.delete(0, tk.END)
            self.sync_folder.insert(0, value)
            self.settings.setdefault("sync", {})["folder"] = value
            self.settings_repo.save(self.settings)

    def _password(self) -> str | None:
        return simpledialog.askstring("Mot de passe", "Mot de passe de chiffrement (8 caractères minimum) :", show="*", parent=self)

    def _push_sync(self) -> None:
        password = self._password()
        if not password:
            return
        try:
            result = self.sync.push(self.sync_folder.get(), password)
        except Exception as exc:
            messagebox.showerror("Synchronisation", str(exc), parent=self)
            return
        self.sync_status.configure(text=f"Snapshot créé : {result.path} ({result.size / 1024 / 1024:.1f} Mo)")

    def _pull_sync(self) -> None:
        snapshots = self.sync.list_snapshots(self.sync_folder.get())
        if not snapshots:
            messagebox.showwarning("Synchronisation", "Aucun snapshot trouvé.", parent=self)
            return
        if not messagebox.askyesno("Restaurer", "Restaurer le snapshot le plus récent ? Une copie de sécurité sera créée.", parent=self):
            return
        password = self._password()
        if not password:
            return
        try:
            result = self.sync.pull(snapshots[0].path, password)
        except Exception as exc:
            messagebox.showerror("Synchronisation", str(exc), parent=self)
            return
        messagebox.showinfo("Synchronisation", f"Restauration terminée. Redémarrez l'application.\nCopie : {result['safety_copy']}", parent=self)

    def _sync_status(self) -> None:
        try:
            result = self.sync.status(self.sync_folder.get())
        except Exception as exc:
            messagebox.showerror("Synchronisation", str(exc), parent=self)
            return
        latest = result.get("latest")
        self.sync_status.configure(text=f"État : {result['state']} · {result['count']} snapshot(s)" + (f" · dernier : {latest.path.name}" if latest else ""))

    # --- Accessibilité ----------------------------------------------
    def _build_accessibility(self) -> None:
        tab = self._tab("♿ Accessibilité")
        config = normalized_accessibility(self.settings)
        ttk.Label(tab, text="Taille du texte").pack(anchor="w", padx=14, pady=(14, 4))
        self.access_scale = tk.DoubleVar(value=config["text_scale"])
        ttk.Scale(tab, from_=0.85, to=1.75, variable=self.access_scale, orient="horizontal").pack(fill="x", padx=14)
        self.access_contrast = tk.BooleanVar(value=config["high_contrast"])
        self.access_focus = tk.BooleanVar(value=config["focus_highlight"])
        self.access_motion = tk.BooleanVar(value=config["reduce_motion"])
        ttk.Checkbutton(tab, text="Contraste renforcé", variable=self.access_contrast).pack(anchor="w", padx=14, pady=8)
        ttk.Checkbutton(tab, text="Mise en évidence du focus clavier", variable=self.access_focus).pack(anchor="w", padx=14, pady=8)
        ttk.Checkbutton(tab, text="Réduire les animations et changements automatiques", variable=self.access_motion).pack(anchor="w", padx=14, pady=8)
        ttk.Button(tab, text="Appliquer", command=self._apply_accessibility, style="Accent.TButton").pack(anchor="w", padx=14, pady=12)
        ttk.Label(tab, text="Raccourcis : Ctrl+K ouvre la recherche ; Tab et Maj+Tab parcourent les contrôles.", wraplength=900).pack(anchor="w", padx=14, pady=8)

    def _apply_accessibility(self) -> None:
        self.settings["accessibility"] = {
            "text_scale": round(self.access_scale.get(), 2),
            "high_contrast": self.access_contrast.get(),
            "focus_highlight": self.access_focus.get(),
            "reduce_motion": self.access_motion.get(),
        }
        self.settings_repo.save(self.settings)
        AccessibilityManager.apply(self.root_window, self.settings)
        if self.on_accessibility_changed:
            self.on_accessibility_changed()
        messagebox.showinfo("Accessibilité", "Réglages appliqués. Certains éléments seront pleinement actualisés au prochain démarrage.", parent=self)

    # --- Extensions --------------------------------------------------
    def _build_plugins(self) -> None:
        tab = self._tab("🧩 Extensions")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self.plugin_tree = ttk.Treeview(tab, columns=("name", "version", "enabled", "compatible", "status"), show="headings")
        for key, title, width in (("name", "Extension", 240), ("version", "Version", 90), ("enabled", "Active", 70), ("compatible", "Compatible", 90), ("status", "État", 360)):
            self.plugin_tree.heading(key, text=title)
            self.plugin_tree.column(key, width=width)
        self.plugin_tree.grid(row=0, column=0, columnspan=4, sticky="nsew", padx=10, pady=8)
        ttk.Button(tab, text="Ouvrir le dossier", command=lambda: webbrowser.open(self.plugins.root.as_uri())).grid(row=1, column=0, padx=5, pady=6)
        ttk.Button(tab, text="Activer / désactiver", command=self._toggle_plugin).grid(row=1, column=1, padx=5, pady=6)
        ttk.Button(tab, text="Charger les extensions actives", command=self._load_plugins, style="Accent.TButton").grid(row=1, column=2, padx=5, pady=6)
        ttk.Label(tab, text="Une extension est du code local : activez uniquement des modules dont vous connaissez l'origine.", wraplength=900).grid(row=2, column=0, columnspan=4, sticky="w", padx=12, pady=8)

    def _toggle_plugin(self) -> None:
        selection = self.plugin_tree.selection()
        if not selection:
            return
        descriptor = next((item for item in self.plugins.discover() if item.plugin_id == selection[0]), None)
        if descriptor:
            if not descriptor.enabled and not messagebox.askyesno("Extension", "Activer ce code local ?", parent=self):
                return
            self.plugins.set_enabled(descriptor.plugin_id, not descriptor.enabled)
            self._refresh_plugins()

    def _load_plugins(self) -> None:
        results = self.plugins.load_enabled()
        messagebox.showinfo("Extensions", "\n".join(f"• {key} : {value}" for key, value in results.items()) or "Aucune extension détectée.", parent=self)
        self._refresh_plugins(results)

    def _refresh_plugins(self, statuses: Mapping[str, str] | None = None) -> None:
        self.plugin_tree.delete(*self.plugin_tree.get_children())
        for item in self.plugins.discover():
            self.plugin_tree.insert("", "end", iid=item.plugin_id, values=(item.name, item.version, "Oui" if item.enabled else "Non", "Oui" if item.compatible else "Non", (statuses or {}).get(item.plugin_id, item.error or "prête")))

    def refresh(self) -> None:
        self.plants = self.database.load_plants()
        labels = [self._plant_label(plant) for plant in self.plants]
        self.plant_by_label = dict(zip(labels, self.plants))
        for combo in (self.location_plant, self.repot_plant, self.compare_plant):
            current = combo.get()
            combo["values"] = labels
            if labels:
                combo.set(current if current in self.plant_by_label else labels[0])
        self._refresh_locations()
        self._refresh_infestations()
        self._refresh_rules()
        self._refresh_photo_choices()
        self._refresh_plugins()


def tk_today() -> str:
    from datetime import date
    return date.today().isoformat()
