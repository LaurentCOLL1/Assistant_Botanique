"""Catalogue botanique consultable et filtrable."""
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import Any, Mapping

from app_data import DATABASE_BY_ID, DATABASE_PLANTES
from core import family_name, normalize_text, profile_id, scientific_name, toxicity_level, vernacular_names


class TabCatalogue(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.filtered_profiles: list[dict[str, Any]] = []
        self.current_photo_url = ""
        self._build_ui()
        self._load_filters()
        self.filtrer_catalogue()

    def _build_ui(self) -> None:
        toolbar = ttk.LabelFrame(self, text=" Recherche et filtres ")
        toolbar.pack(fill="x", padx=10, pady=(8, 4))
        toolbar.columnconfigure(1, weight=1)
        toolbar.columnconfigure(3, weight=1)
        ttk.Label(toolbar, text="Texte").grid(row=0, column=0, sticky="w", padx=5, pady=4)
        self.entry_search = ttk.Entry(toolbar)
        self.entry_search.grid(row=0, column=1, sticky="ew", padx=5, pady=4)
        self.entry_search.bind("<KeyRelease>", self.filtrer_catalogue)
        ttk.Label(toolbar, text="Famille").grid(row=0, column=2, sticky="w", padx=5, pady=4)
        self.combo_family = ttk.Combobox(toolbar, state="readonly")
        self.combo_family.grid(row=0, column=3, sticky="ew", padx=5, pady=4)
        self.combo_family.bind("<<ComboboxSelected>>", self.filtrer_catalogue)
        ttk.Label(toolbar, text="Toxicité").grid(row=0, column=4, sticky="w", padx=5, pady=4)
        self.combo_toxicity = ttk.Combobox(
            toolbar,
            state="readonly",
            width=15,
            values=("Toutes", "aucune", "faible", "moderee", "elevee", "inconnue"),
        )
        self.combo_toxicity.grid(row=0, column=5, sticky="ew", padx=5, pady=4)
        self.combo_toxicity.set("Toutes")
        self.combo_toxicity.bind("<<ComboboxSelected>>", self.filtrer_catalogue)

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        left = ttk.LabelFrame(paned, text=" Espèces ")
        right = ttk.LabelFrame(paned, text=" Fiche détaillée ")
        paned.add(left, weight=1)
        paned.add(right, weight=3)

        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical")
        self.listbox = tk.Listbox(list_frame, exportselection=False, yscrollcommand=list_scroll.set)
        list_scroll.configure(command=self.listbox.yview)
        self.listbox.pack(side="left", fill="both", expand=True)
        list_scroll.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self._on_selection)
        self.counter = ttk.Label(left, text="0 espèce", style="Muted.TLabel")
        self.counter.pack(anchor="e", padx=6, pady=(0, 5))

        photo_bar = ttk.Frame(right)
        photo_bar.pack(fill="x", padx=8, pady=(6, 0))
        self.photo_label = ttk.Label(
            photo_bar,
            text="Photo : non renseignée",
            style="Muted.TLabel",
            wraplength=760,
        )
        self.photo_label.pack(side="left", fill="x", expand=True)
        self.photo_button = ttk.Button(
            photo_bar,
            text="Ouvrir la photo source",
            command=self._open_photo_source,
            state="disabled",
        )
        self.photo_button.pack(side="right", padx=(8, 0))

        text_frame = ttk.Frame(right)
        text_frame.pack(fill="both", expand=True, padx=5, pady=5)
        text_scroll = ttk.Scrollbar(text_frame, orient="vertical")
        self.text = tk.Text(
            text_frame,
            wrap="word",
            state="disabled",
            padx=12,
            pady=10,
            yscrollcommand=text_scroll.set,
        )
        text_scroll.configure(command=self.text.yview)
        self.text.pack(side="left", fill="both", expand=True)
        text_scroll.pack(side="right", fill="y")
        self.text.tag_configure("title", font=("Segoe UI", 15, "bold"), foreground="#287848")
        self.text.tag_configure("section", font=("Segoe UI", 11, "bold"), spacing1=10, spacing3=4)
        self.text.tag_configure("label", font=("Segoe UI", 9, "bold"))
        self.text.tag_configure("danger", foreground="#b00020", font=("Segoe UI", 9, "bold"))
        self.text.tag_configure("muted", foreground="#666666", font=("Segoe UI", 8, "italic"))

    def _load_filters(self) -> None:
        families = sorted({family_name(profile) for profile in DATABASE_PLANTES}, key=normalize_text)
        self.combo_family["values"] = ("Toutes", *families)
        self.combo_family.set("Toutes")

    def filtrer_catalogue(self, event=None) -> None:
        query = normalize_text(self.entry_search.get())
        family_filter = self.combo_family.get() or "Toutes"
        toxicity_filter = self.combo_toxicity.get() or "Toutes"
        result: list[dict[str, Any]] = []
        for profile in DATABASE_PLANTES:
            tax = profile.get("taxonomie", {})
            health = profile.get("sante_securite", {})
            toxicity = toxicity_level(health.get("toxicite") if isinstance(health, Mapping) else None)
            haystack = " ".join(
                [
                    scientific_name(profile),
                    ", ".join(vernacular_names(profile)),
                    family_name(profile),
                    str(tax.get("origine_geographique", "")),
                    str(profile.get("conseil", "")),
                ]
            )
            if query and query not in normalize_text(haystack):
                continue
            if family_filter != "Toutes" and family_name(profile) != family_filter:
                continue
            if toxicity_filter != "Toutes" and toxicity != toxicity_filter:
                continue
            result.append(profile)
        self.filtered_profiles = result
        self.listbox.delete(0, tk.END)
        for profile in result:
            vernacular = ", ".join(vernacular_names(profile))
            self.listbox.insert(
                tk.END,
                f"{scientific_name(profile)}" + (f" — {vernacular}" if vernacular else ""),
            )
        self.counter.configure(text=f"{len(result)} espèce(s)")
        if result:
            self.listbox.selection_set(0)
            self._on_selection()
        else:
            self._set_photo(None)
            self._write_text("Aucune espèce ne correspond aux filtres.")

    def _on_selection(self, event=None) -> None:
        selection = self.listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if 0 <= index < len(self.filtered_profiles):
            self.afficher_fiche_botanique(self.filtered_profiles[index])

    def selectionner_plante(self, species_identifier: str) -> None:
        profile = DATABASE_BY_ID.get(species_identifier)
        if not profile:
            normalized_target = normalize_text(species_identifier)
            profile = next(
                (
                    item
                    for item in DATABASE_PLANTES
                    if normalize_text(scientific_name(item)) == normalized_target
                ),
                None,
            )
        if not profile:
            return
        self.entry_search.delete(0, tk.END)
        self.entry_search.insert(0, scientific_name(profile))
        self.combo_family.set("Toutes")
        self.combo_toxicity.set("Toutes")
        self.filtrer_catalogue()
        for index, item in enumerate(self.filtered_profiles):
            if profile_id(item) == profile_id(profile):
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(index)
                self.listbox.see(index)
                self.afficher_fiche_botanique(item)
                break

    selectionner_plante_par_nom_sci = selectionner_plante

    @staticmethod
    def _nested(profile: Mapping[str, Any], *path: str, default: Any = "Non renseigné") -> Any:
        current: Any = profile
        for key in path:
            if not isinstance(current, Mapping) or key not in current:
                return default
            current = current[key]
        return current if current not in (None, "") else default

    def _insert_field(self, label: str, value: Any, *, danger: bool = False, hide_empty: bool = False) -> None:
        if value in (None, "", [], "Non renseigné") and hide_empty:
            return
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        if isinstance(value, Mapping):
            value = "; ".join(f"{key}: {val}" for key, val in value.items())
        self.text.insert(tk.END, f"• {label} : ", "label")
        self.text.insert(tk.END, f"{value}\n", "danger" if danger else None)

    def _insert_section(self, title: str) -> None:
        self.text.insert(tk.END, f"\n{title}\n", "section")

    def _set_photo(self, photo: Mapping[str, Any] | None) -> None:
        self.current_photo_url = ""
        self.photo_button.configure(state="disabled")
        if not photo or photo.get("status") == "not_found":
            self.photo_label.configure(text="Photo : aucune image traçable trouvée")
            return
        source = str(photo.get("source") or "source inconnue")
        license_name = str(photo.get("license") or "licence à vérifier")
        representative = photo.get("status") == "representative" or photo.get("representative") is True
        prefix = "Photo représentative" if representative else "Photo identifiée"
        self.photo_label.configure(text=f"{prefix} — {source} — {license_name}")
        page_url = str(photo.get("page_url") or "").strip()
        if page_url:
            self.current_photo_url = page_url
            self.photo_button.configure(state="normal")

    def _open_photo_source(self) -> None:
        if self.current_photo_url:
            webbrowser.open(self.current_photo_url)

    def afficher_fiche_botanique(self, profile: Mapping[str, Any]) -> None:
        photo = profile.get("photo") if isinstance(profile.get("photo"), Mapping) else None
        self._set_photo(photo)
        self.text.configure(state="normal")
        self.text.delete("1.0", tk.END)
        vernacular = ", ".join(vernacular_names(profile))
        self.text.insert(tk.END, scientific_name(profile) + "\n", "title")
        if vernacular:
            self.text.insert(tk.END, vernacular + "\n")
        self.text.insert(tk.END, f"ID : {profile_id(profile)}\n", "muted")

        self._insert_section("1. Taxonomie et origine")
        self._insert_field("Famille", family_name(profile))
        self._insert_field("Origine", self._nested(profile, "taxonomie", "origine_geographique"))

        self._insert_section("2. Morphologie")
        self._insert_field("Port", self._nested(profile, "morphologie", "port"))
        self._insert_field("Système racinaire", self._nested(profile, "morphologie", "systeme_racinaire"))
        self._insert_field("Feuillage", self._nested(profile, "morphologie", "feuillage", "morphologie"))
        self._insert_field("Coloris et motifs", self._nested(profile, "morphologie", "feuillage", "coloris_motifs"))
        self._insert_field("Floraison", self._nested(profile, "morphologie", "floraison"))
        self._insert_field("Fleurs", self._nested(profile, "morphologie", "fleurs", "description"))
        self._insert_field("Fruits et graines", self._nested(profile, "morphologie", "fruits_graines"))

        self._insert_section("3. Conditions de culture")
        self._insert_field("Exposition", self._nested(profile, "exigences_climatiques", "exposition"))
        self._insert_field("Température idéale", self._nested(profile, "exigences_climatiques", "temperature_ideale"))
        self._insert_field("Rusticité", self._nested(profile, "exigences_climatiques", "rusticite"))
        self._insert_field("Hygrométrie", self._nested(profile, "exigences_climatiques", "hygrometrie"))

        self._insert_section("4. Eau — intervalles indicatifs")
        self._insert_field("Consigne générale", self._nested(profile, "gestion_eau", "frequence_mode"))
        frequency = self._nested(profile, "gestion_eau", "frequence_arrosage", default={})
        if isinstance(frequency, Mapping):
            months = [
                "janvier", "fevrier", "mars", "avril", "mai", "juin",
                "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
            ]
            self._insert_field(
                "Calendrier",
                " | ".join(f"{month[:3]}. {frequency.get(month, '?')} j" for month in months),
            )
        self._insert_field("Qualité d'eau", self._nested(profile, "gestion_eau", "qualite_eau"))
        self.text.insert(
            tk.END,
            "Ces intervalles sont des rappels de contrôle : vérifier le substrat avant d'arroser.\n",
            "muted",
        )

        self._insert_section("5. Substrat")
        self._insert_field("Composition", self._nested(profile, "substrat", "composition_ideale"))
        self._insert_field("pH", self._nested(profile, "substrat", "ph"))
        self._insert_field("Ingrédients recommandés", self._nested(profile, "substrat", "ingredients_recommandes"))
        self._insert_field("À éviter", self._nested(profile, "substrat", "elements_interdits"))

        self._insert_section("6. Entretien")
        for key, label in (
            ("rempotage", "Rempotage"),
            ("fertilisation", "Fertilisation"),
            ("taille", "Taille"),
            ("multiplication", "Multiplication"),
        ):
            self._insert_field(label, self._nested(profile, "entretien", key))

        self._insert_section("7. Santé et sécurité")
        toxicity = self._nested(profile, "sante_securite", "toxicite")
        level = toxicity_level(toxicity)
        self._insert_field(
            "Toxicité",
            f"{toxicity} — niveau normalisé : {level}",
            danger=level in {"moderee", "elevee"},
        )
        self._insert_field("Maladies", self._nested(profile, "sante_securite", "maladies"))
        self._insert_field("Ravageurs", self._nested(profile, "sante_securite", "ravageurs"))
        self._insert_field(
            "Propriétés particulières",
            self._nested(profile, "sante_securite", "proprietes_particulieres"),
            hide_empty=True,
        )

        advice = profile.get("conseil")
        if advice:
            self._insert_section("8. Conseil")
            self.text.insert(tk.END, str(advice) + "\n")

        self._insert_section("9. Photographie")
        if photo and photo.get("status") != "not_found":
            self._insert_field("Statut", "Représentative" if photo.get("status") == "representative" else "Taxon identifié")
            self._insert_field("Source", photo.get("source") or "Non renseignée")
            self._insert_field("Auteur", photo.get("author") or "Non renseigné")
            self._insert_field("Licence", photo.get("license") or "À vérifier")
            self._insert_field("Attribution", photo.get("attribution") or "Non renseignée")
        else:
            self.text.insert(tk.END, "Aucune photo avec provenance et licence exploitables n'a été trouvée.\n", "muted")

        metadata = profile.get("metadata", {})
        self._insert_section("10. Traçabilité")
        self._insert_field("Fichier source", metadata.get("source_file", "Non renseigné"))
        self._insert_field("Niveau de confiance", metadata.get("confidence", "non_renseignee"))
        self._insert_field("Dernière révision", metadata.get("last_reviewed") or "Non renseignée")
        self._insert_field("Sources", metadata.get("sources") or "À compléter")

        audit = profile.get("catalogue_audit")
        if isinstance(audit, Mapping):
            taxonomic = audit.get("taxonomic") if isinstance(audit.get("taxonomic"), Mapping) else {}
            structure = audit.get("structure") if isinstance(audit.get("structure"), Mapping) else {}
            self._insert_field("Contrôle taxonomique", taxonomic.get("status") or "Non renseigné")
            self._insert_field("Nom accepté", taxonomic.get("accepted_scientific_name") or taxonomic.get("canonical_name") or "Non renseigné")
            self._insert_field("Famille concordante", "Oui" if taxonomic.get("family_consistent") is True else "À vérifier")
            self._insert_field("Structure complète", "Oui" if structure.get("complete") is True else "Non")
            self._insert_field("Audit effectué le", audit.get("reviewed_at") or "Non renseigné")
        self.text.configure(state="disabled")

    def _write_text(self, value: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", value)
        self.text.configure(state="disabled")
