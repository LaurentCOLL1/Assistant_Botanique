"""Onglet de gestion de la collection personnelle."""
from __future__ import annotations

import csv
import logging
import tkinter as tk
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from uuid import uuid4

from app_data import COLLECTION_INITIALE_DEFAUT, DATABASE_BY_ID, DATABASE_BY_SCIENTIFIC_NAME, DATABASE_PLANTES
from core import (
    ValidationError,
    family_name,
    format_date_fr,
    normalize_text,
    parse_date,
    profile_id,
    scientific_name,
    vernacular_names,
    watering_status,
)
from storage import CollectionRepository

LOGGER = logging.getLogger(__name__)


class TabGestion(ttk.Frame):
    def __init__(self, parent, on_collection_changed_callback=None, voir_catalogue_callback=None):
        super().__init__(parent)
        self.on_collection_changed_callback = on_collection_changed_callback
        self.voir_catalogue_callback = voir_catalogue_callback
        self.repository = CollectionRepository()
        self.mes_plantes: list[dict] = []
        self.historique: list[list[dict]] = []
        self.search_results: list[dict] = []
        self._build_ui()
        self._load_collection()
        self.winfo_toplevel().bind("<Control-z>", self.annuler_action)
        self.winfo_toplevel().bind("<Control-Z>", self.annuler_action)

    def _build_ui(self) -> None:
        form = ttk.LabelFrame(self, text=" Ajouter ou modifier une plante ")
        form.pack(fill="x", padx=10, pady=(8, 4))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        ttk.Label(form, text="Surnom").grid(row=0, column=0, sticky="w", padx=5, pady=4)
        self.entry_surnom = ttk.Entry(form)
        self.entry_surnom.grid(row=0, column=1, sticky="ew", padx=5, pady=4)
        self.entry_surnom.insert(0, "Ma nouvelle plante")

        ttk.Label(form, text="Volume du pot (L)").grid(row=0, column=2, sticky="w", padx=5, pady=4)
        self.entry_pot = ttk.Entry(form, width=12)
        self.entry_pot.grid(row=0, column=3, sticky="w", padx=5, pady=4)
        self.entry_pot.insert(0, "1.5")

        ttk.Label(form, text="Emplacement").grid(row=1, column=0, sticky="w", padx=5, pady=4)
        self.combo_emplacement = ttk.Combobox(form, state="readonly", values=("interieur", "exterieur", "serre"))
        self.combo_emplacement.grid(row=1, column=1, sticky="ew", padx=5, pady=4)
        self.combo_emplacement.set("interieur")

        ttk.Label(form, text="Exposition").grid(row=1, column=2, sticky="w", padx=5, pady=4)
        self.combo_exposition = ttk.Combobox(
            form,
            state="readonly",
            values=("non_renseignee", "ombre", "mi_ombre", "lumiere_vive", "soleil_direct"),
        )
        self.combo_exposition.grid(row=1, column=3, sticky="ew", padx=5, pady=4)
        self.combo_exposition.set("non_renseignee")

        ttk.Label(form, text="Recherche espèce, famille ou origine").grid(row=2, column=0, columnspan=4, sticky="w", padx=5)
        self.entry_search = ttk.Entry(form)
        self.entry_search.grid(row=3, column=0, columnspan=4, sticky="ew", padx=5, pady=3)
        self.entry_search.bind("<KeyRelease>", self.filtrer_recherche)

        self.listbox_plantes = tk.Listbox(form, height=4, exportselection=False)
        self.listbox_plantes.grid(row=4, column=0, columnspan=4, sticky="ew", padx=5, pady=3)
        self.listbox_plantes.bind("<Double-Button-1>", lambda _event: self.ajouter_plante())

        buttons = ttk.Frame(form)
        buttons.grid(row=5, column=0, columnspan=4, sticky="e", padx=5, pady=5)
        ttk.Button(buttons, text="➕ Ajouter", command=self.ajouter_plante, style="Accent.TButton").pack(side="left", padx=3)
        ttk.Button(buttons, text="✏️ Appliquer aux données sélectionnées", command=self.modifier_plante).pack(side="left", padx=3)
        ttk.Button(buttons, text="Réinitialiser le formulaire", command=self.reset_form).pack(side="left", padx=3)

        collection = ttk.LabelFrame(self, text=" Ma collection — rappel de contrôle du substrat ")
        collection.pack(fill="both", expand=True, padx=10, pady=4)
        columns = ("nickname", "scientific", "family", "pot", "last", "next", "status")
        self.tree = ttk.Treeview(collection, columns=columns, show="headings", selectmode="extended")
        headings = {
            "nickname": "Surnom", "scientific": "Nom scientifique", "family": "Famille",
            "pot": "Pot (L)", "last": "Dernier arrosage", "next": "Prochain contrôle", "status": "Statut",
        }
        widths = {"nickname": 150, "scientific": 190, "family": 130, "pot": 65, "last": 105, "next": 110, "status": 180}
        for column in columns:
            self.tree.heading(column, text=headings[column], command=lambda c=column: self.sort_tree(c, False))
            self.tree.column(column, width=widths[column], anchor="w" if column not in {"pot", "last", "next"} else "center")
        scrollbar = ttk.Scrollbar(collection, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)
        scrollbar.pack(side="right", fill="y", padx=(0, 5), pady=5)
        self.tree.bind("<<TreeviewSelect>>", self.afficher_details_plante)
        self.tree.bind("<Double-Button-1>", lambda _event: self.modifier_plante())
        self.tree.tag_configure("OK", foreground="#287848")
        self.tree.tag_configure("TODAY", foreground="#b45f06")
        self.tree.tag_configure("LATE", foreground="#b00020")
        self.tree.tag_configure("REST", foreground="#1b6ca8")
        self.tree.tag_configure("MISSING", foreground="#777777")

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=10, pady=4)
        ttk.Button(actions, text="💧 Enregistrer un arrosage", command=self.marquer_arrosee_aujourdhui, style="Accent.TButton").pack(side="left", padx=3)
        ttk.Button(actions, text="📝 Ajouter un soin", command=self.ajouter_soin).pack(side="left", padx=3)
        ttk.Button(actions, text="📅 Calendrier", command=self.ouvrir_fenetre_calendrier).pack(side="left", padx=3)
        ttk.Button(actions, text="CSV", command=self.exporter_csv).pack(side="left", padx=3)
        ttk.Button(actions, text="iCalendar", command=self.exporter_ics).pack(side="left", padx=3)
        ttk.Button(actions, text="📖 Voir la fiche", command=self.aller_au_catalogue).pack(side="right", padx=3)
        ttk.Button(actions, text="🗑️ Supprimer", command=self.supprimer_plante, style="Danger.TButton").pack(side="right", padx=3)

        details = ttk.LabelFrame(self, text=" Détails, contexte et historique ")
        details.pack(fill="both", padx=10, pady=(4, 8))
        self.txt_details = tk.Text(details, height=9, wrap="word", state="disabled")
        self.txt_details.pack(fill="both", expand=True, padx=6, pady=6)

        self.filtrer_recherche()

    def _load_collection(self) -> None:
        try:
            self.mes_plantes = self.repository.load(COLLECTION_INITIALE_DEFAUT)
            changed = False
            for plant in self.mes_plantes:
                profile = self.resolve_profile(plant.get("species_id", ""))
                if profile and plant.get("species_id") != profile_id(profile):
                    plant["species_id"] = profile_id(profile)
                    changed = True
            if changed:
                self.repository.save(self.mes_plantes)
        except (OSError, ValidationError) as exc:
            LOGGER.exception("Impossible de charger la collection")
            messagebox.showerror("Collection", str(exc))
            self.mes_plantes = []
        self.rafraichir_tableau_collection()

    @staticmethod
    def resolve_profile(identifier: str) -> dict | None:
        return DATABASE_BY_ID.get(identifier) or DATABASE_BY_SCIENTIFIC_NAME.get(identifier)

    def save_collection(self) -> bool:
        try:
            self.repository.save(self.mes_plantes)
        except (OSError, ValidationError) as exc:
            LOGGER.exception("Échec de sauvegarde")
            messagebox.showerror("Sauvegarde", str(exc))
            return False
        if self.on_collection_changed_callback:
            self.on_collection_changed_callback(self.mes_plantes)
        return True

    def enregistrer_historique(self) -> None:
        self.historique.append(deepcopy(self.mes_plantes))
        self.historique = self.historique[-20:]

    def annuler_action(self, event=None):
        focused = self.focus_get()
        if isinstance(focused, (tk.Entry, ttk.Entry, tk.Text)):
            return
        if not self.historique:
            messagebox.showinfo("Annulation", "Aucune action à annuler.")
            return
        previous = self.historique.pop()
        current = self.mes_plantes
        self.mes_plantes = previous
        if not self.save_collection():
            self.mes_plantes = current
            return
        self.rafraichir_tableau_collection()

    def filtrer_recherche(self, event=None) -> None:
        query = normalize_text(self.entry_search.get())
        self.listbox_plantes.delete(0, tk.END)
        self.search_results = []
        for profile in DATABASE_PLANTES:
            tax = profile.get("taxonomie", {})
            haystack = " ".join(
                [scientific_name(profile), ", ".join(vernacular_names(profile)), family_name(profile), str(tax.get("origine_geographique", ""))]
            )
            if query and query not in normalize_text(haystack):
                continue
            self.search_results.append(profile)
            vernacular = ", ".join(vernacular_names(profile))
            self.listbox_plantes.insert(tk.END, f"{scientific_name(profile)} — {vernacular or 'sans nom vernaculaire'}")
        if self.search_results:
            self.listbox_plantes.selection_set(0)

    def _validated_form(self) -> tuple[str, float, dict]:
        nickname = self.entry_surnom.get().strip()
        if not nickname:
            raise ValidationError("Le surnom ne peut pas être vide.")
        try:
            pot_l = float(self.entry_pot.get().strip().replace(",", "."))
        except ValueError as exc:
            raise ValidationError("Le volume du pot doit être un nombre.") from exc
        if pot_l <= 0 or pot_l > 100000:
            raise ValidationError("Le volume du pot doit être positif et réaliste.")
        context = {
            "emplacement": self.combo_emplacement.get() or "interieur",
            "exposition": self.combo_exposition.get() or "non_renseignee",
            "matiere_pot": "non_renseignee",
            "substrat": "non_renseigne",
        }
        return nickname, pot_l, context

    def ajouter_plante(self) -> None:
        selection = self.listbox_plantes.curselection()
        if not selection:
            messagebox.showwarning("Ajout", "Sélectionnez une espèce dans les résultats.")
            return
        try:
            nickname, pot_l, context = self._validated_form()
            profile = self.search_results[selection[0]]
        except (ValidationError, IndexError) as exc:
            messagebox.showerror("Ajout", str(exc))
            return
        self.enregistrer_historique()
        today = format_date_fr(date.today())
        plant = {
            "id": str(uuid4()),
            "species_id": profile_id(profile),
            "surnom": nickname,
            "pot_l": pot_l,
            "date_arrosage": today,
            "historique_soins": [{"type": "arrosage", "date": today, "note": "Création dans la collection"}],
            "contexte": context,
        }
        self.mes_plantes.append(plant)
        if not self.save_collection():
            self.mes_plantes.pop()
            self.historique.pop()
            return
        self.rafraichir_tableau_collection(select_id=plant["id"])

    def modifier_plante(self) -> None:
        selected = self.tree.selection()
        if len(selected) != 1:
            messagebox.showwarning("Modification", "Sélectionnez exactement une plante.")
            return
        try:
            nickname, pot_l, context = self._validated_form()
        except ValidationError as exc:
            messagebox.showerror("Modification", str(exc))
            return
        plant = self.find_instance(selected[0])
        if not plant:
            return
        self.enregistrer_historique()
        old = deepcopy(plant)
        plant.update({"surnom": nickname, "pot_l": pot_l, "contexte": context})
        if not self.save_collection():
            plant.clear()
            plant.update(old)
            self.historique.pop()
            return
        self.rafraichir_tableau_collection(select_id=plant["id"])

    def reset_form(self) -> None:
        self.entry_surnom.delete(0, tk.END)
        self.entry_surnom.insert(0, "Ma nouvelle plante")
        self.entry_pot.delete(0, tk.END)
        self.entry_pot.insert(0, "1.5")
        self.combo_emplacement.set("interieur")
        self.combo_exposition.set("non_renseignee")

    def find_instance(self, instance_id: str) -> dict | None:
        return next((plant for plant in self.mes_plantes if plant.get("id") == instance_id), None)

    def rafraichir_tableau_collection(self, select_id: str | None = None) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for plant in self.mes_plantes:
            profile = self.resolve_profile(plant.get("species_id", ""))
            if not profile:
                self.tree.insert(
                    "", "end", iid=plant["id"],
                    values=(plant["surnom"], plant.get("species_id", "Espèce inconnue"), "—", plant["pot_l"], plant["date_arrosage"], "—", "⚠️ Fiche introuvable"),
                    tags=("MISSING",),
                )
                continue
            try:
                status = watering_status(plant["date_arrosage"], profile)
                next_check = format_date_fr(status.next_check) if status.next_check else "Repos"
                tag = status.code
                label = status.short_label
            except ValidationError as exc:
                next_check, tag, label = "Erreur", "MISSING", str(exc)
            self.tree.insert(
                "", "end", iid=plant["id"],
                values=(
                    plant["surnom"], scientific_name(profile), family_name(profile), f"{float(plant['pot_l']):g}",
                    plant["date_arrosage"], next_check, label,
                ),
                tags=(tag,),
            )
        if select_id and self.tree.exists(select_id):
            self.tree.selection_set(select_id)
            self.tree.see(select_id)
        self.afficher_details_plante()

    def sort_tree(self, column: str, reverse: bool) -> None:
        rows = [(self.tree.set(item, column), item) for item in self.tree.get_children("")]
        if column == "pot":
            rows.sort(key=lambda pair: float(pair[0] or 0), reverse=reverse)
        else:
            rows.sort(key=lambda pair: normalize_text(pair[0]), reverse=reverse)
        for index, (_, item) in enumerate(rows):
            self.tree.move(item, "", index)
        self.tree.heading(column, command=lambda: self.sort_tree(column, not reverse))

    def afficher_details_plante(self, event=None) -> None:
        selected = self.tree.selection()
        text = "Sélectionnez une plante."
        if len(selected) == 1:
            plant = self.find_instance(selected[0])
            if plant:
                profile = self.resolve_profile(plant.get("species_id", ""))
                context = plant.get("contexte", {})
                lines = [f"Identifiant : {plant['id']}", f"Surnom : {plant['surnom']}"]
                if profile:
                    lines.extend([
                        f"Espèce : {scientific_name(profile)} ({', '.join(vernacular_names(profile))})",
                        f"Famille : {family_name(profile)}",
                    ])
                    try:
                        status = watering_status(plant["date_arrosage"], profile)
                        lines.append(f"Rappel : {status.detail}")
                    except ValidationError as exc:
                        lines.append(f"Erreur de calendrier : {exc}")
                else:
                    lines.append("⚠️ La fiche de cette espèce n'existe plus dans le catalogue ; l'exemplaire est conservé.")
                lines.append(f"Contexte : {context.get('emplacement')} — {context.get('exposition')} — pot {plant['pot_l']} L")
                history = plant.get("historique_soins", [])
                lines.append("\nHistorique récent :")
                for event_item in history[-8:][::-1]:
                    lines.append(f"• {event_item.get('date', '?')} — {event_item.get('type', 'soin')} : {event_item.get('note', '')}")
                text = "\n".join(lines)
                self.entry_surnom.delete(0, tk.END)
                self.entry_surnom.insert(0, plant["surnom"])
                self.entry_pot.delete(0, tk.END)
                self.entry_pot.insert(0, f"{float(plant['pot_l']):g}")
                self.combo_emplacement.set(context.get("emplacement", "interieur"))
                self.combo_exposition.set(context.get("exposition", "non_renseignee"))
        self.txt_details.config(state="normal")
        self.txt_details.delete("1.0", tk.END)
        self.txt_details.insert("1.0", text)
        self.txt_details.config(state="disabled")

    def marquer_arrosee_aujourdhui(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Arrosage", "Sélectionnez au moins une plante.")
            return
        self.enregistrer_historique()
        today = format_date_fr(date.today())
        for instance_id in selected:
            plant = self.find_instance(instance_id)
            if not plant:
                continue
            plant["date_arrosage"] = today
            plant.setdefault("historique_soins", []).append({"type": "arrosage", "date": today, "note": "Arrosage enregistré"})
        if not self.save_collection():
            self.mes_plantes = self.historique.pop()
            return
        self.rafraichir_tableau_collection(select_id=selected[0])

    def ajouter_soin(self) -> None:
        selected = self.tree.selection()
        if len(selected) != 1:
            messagebox.showwarning("Soin", "Sélectionnez exactement une plante.")
            return
        care_type = simpledialog.askstring("Type de soin", "Type : rempotage, engrais, taille, observation…", parent=self)
        if not care_type:
            return
        note = simpledialog.askstring("Note", "Détail du soin ou de l'observation :", parent=self) or ""
        date_text = simpledialog.askstring("Date", "Date au format JJ/MM/AAAA :", initialvalue=format_date_fr(date.today()), parent=self)
        if not date_text:
            return
        try:
            care_date = parse_date(date_text)
            if care_date > date.today():
                raise ValidationError("La date du soin ne peut pas être dans le futur.")
        except ValidationError as exc:
            messagebox.showerror("Soin", str(exc))
            return
        plant = self.find_instance(selected[0])
        if not plant:
            return
        self.enregistrer_historique()
        plant.setdefault("historique_soins", []).append({"type": care_type.strip(), "date": format_date_fr(care_date), "note": note.strip()})
        if not self.save_collection():
            self.mes_plantes = self.historique.pop()
            return
        self.afficher_details_plante()

    def supprimer_plante(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Suppression", "Sélectionnez au moins une plante.")
            return
        if not messagebox.askyesno("Suppression", f"Supprimer {len(selected)} exemplaire(s) ?"):
            return
        self.enregistrer_historique()
        selected_ids = set(selected)
        old = self.mes_plantes
        self.mes_plantes = [plant for plant in self.mes_plantes if plant.get("id") not in selected_ids]
        if not self.save_collection():
            self.mes_plantes = old
            self.historique.pop()
            return
        self.rafraichir_tableau_collection()

    def aller_au_catalogue(self) -> None:
        selected = self.tree.selection()
        if len(selected) != 1:
            messagebox.showwarning("Catalogue", "Sélectionnez exactement une plante.")
            return
        plant = self.find_instance(selected[0])
        if plant and self.voir_catalogue_callback:
            self.voir_catalogue_callback(plant.get("species_id", ""))

    def _planning(self, start: date, end: date) -> dict[date, list[str]]:
        planning: dict[date, list[str]] = {}
        for plant in self.mes_plantes:
            profile = self.resolve_profile(plant.get("species_id", ""))
            if not profile:
                continue
            current = parse_date(plant["date_arrosage"])
            safety = 0
            while current <= end and safety < 1000:
                safety += 1
                status = watering_status(current, profile, today=current)
                interval = status.interval_days
                if interval == 0:
                    current = date(current.year + (current.month == 12), 1 if current.month == 12 else current.month + 1, 1)
                    continue
                current += timedelta(days=interval)
                if start <= current <= end:
                    planning.setdefault(current, []).append(plant["surnom"])
        return planning

    def ouvrir_fenetre_calendrier(self) -> None:
        window = tk.Toplevel(self)
        window.title("Calendrier indicatif de contrôle")
        window.geometry("760x560")
        controls = ttk.Frame(window)
        controls.pack(fill="x", padx=8, pady=8)
        ttk.Label(controls, text="Début").pack(side="left")
        start_entry = ttk.Entry(controls, width=12)
        start_entry.insert(0, format_date_fr(date.today()))
        start_entry.pack(side="left", padx=4)
        ttk.Label(controls, text="Fin").pack(side="left")
        end_entry = ttk.Entry(controls, width=12)
        end_entry.insert(0, format_date_fr(date.today() + timedelta(days=30)))
        end_entry.pack(side="left", padx=4)
        result = tk.Text(window, wrap="word")
        result.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        def generate() -> None:
            try:
                start = parse_date(start_entry.get())
                end = parse_date(end_entry.get())
                if end < start:
                    raise ValidationError("La date de fin doit être postérieure à la date de début.")
                if (end - start).days > 730:
                    raise ValidationError("La période est limitée à deux ans.")
                planning = self._planning(start, end)
            except ValidationError as exc:
                messagebox.showerror("Calendrier", str(exc), parent=window)
                return
            lines = ["RAPPELS DE CONTRÔLE DU SUBSTRAT", "Arroser uniquement après vérification de l'humidité et de l'état de la plante.", ""]
            for day, names in sorted(planning.items()):
                lines.append(f"{format_date_fr(day)} : {', '.join(names)}")
            if not planning:
                lines.append("Aucun contrôle prévu sur cette période.")
            result.delete("1.0", tk.END)
            result.insert("1.0", "\n".join(lines))

        ttk.Button(controls, text="Générer", command=generate).pack(side="left", padx=6)
        generate()

    def exporter_csv(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="collection_botanique.csv")
        if not path:
            return
        try:
            with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(["id", "surnom", "nom_scientifique", "famille", "pot_l", "dernier_arrosage", "emplacement", "exposition"])
                for plant in self.mes_plantes:
                    profile = self.resolve_profile(plant.get("species_id", ""))
                    context = plant.get("contexte", {})
                    writer.writerow([
                        plant["id"], plant["surnom"], scientific_name(profile or {"nom_sci": plant.get("species_id")}),
                        family_name(profile or {}), plant["pot_l"], plant["date_arrosage"],
                        context.get("emplacement", ""), context.get("exposition", ""),
                    ])
        except OSError as exc:
            messagebox.showerror("Export CSV", str(exc))

    def exporter_ics(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".ics", filetypes=[("iCalendar", "*.ics")], initialfile="controles_plantes.ics")
        if not path:
            return
        planning = self._planning(date.today(), date.today() + timedelta(days=365))
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Assistant Botanique//FR"]
        for day, names in sorted(planning.items()):
            uid = f"{day.isoformat()}-{'-'.join(normalize_text(name).replace(' ', '-') for name in names)}@assistant-botanique"
            lines.extend([
                "BEGIN:VEVENT", f"UID:{uid}", f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
                f"SUMMARY:Contrôler le substrat — {', '.join(names)}",
                "DESCRIPTION:Vérifier l'humidité du substrat et l'état de la plante avant tout arrosage.",
                "END:VEVENT",
            ])
        lines.append("END:VCALENDAR")
        try:
            Path(path).write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Export iCalendar", str(exc))
