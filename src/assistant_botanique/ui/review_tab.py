"""Onglet de révision et validation botanique."""
from __future__ import annotations

import json
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk
from typing import Any, Callable

from core import scientific_name
from assistant_botanique.infrastructure.catalogue import catalogue_review_score, save_override, validate_profile
from assistant_botanique.infrastructure.database import Database


class CatalogueReviewTab(ttk.Frame):
    STATUSES = ("brouillon", "a_verifier", "valide", "rejete")
    CONFIDENCES = ("non_renseignee", "faible", "moyenne", "elevee")

    def __init__(
        self,
        parent,
        database: Database,
        catalogue: list[dict[str, Any]],
        reload_catalogue: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self.database = database
        self.catalogue = catalogue
        self.reload_catalogue_callback = reload_catalogue
        self.filtered = list(catalogue)
        self._build_ui()
        self._refresh_species()

    def _build_ui(self) -> None:
        selector = ttk.Frame(self)
        selector.pack(fill="x", padx=12, pady=10)
        ttk.Label(selector, text="Rechercher une espèce").pack(side="left")
        self.search_var = tk.StringVar()
        search = ttk.Entry(selector, textvariable=self.search_var, width=35)
        search.pack(side="left", padx=6)
        search.bind("<KeyRelease>", lambda _e: self._refresh_species())
        self.combo = ttk.Combobox(selector, state="readonly", width=52)
        self.combo.pack(side="left", padx=6, fill="x", expand=True)
        self.combo.bind("<<ComboboxSelected>>", lambda _e: self.load_selected())

        metadata = ttk.LabelFrame(self, text=" Workflow de validation ")
        metadata.pack(fill="x", padx=12, pady=5)
        ttk.Label(metadata, text="Statut").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.status = ttk.Combobox(metadata, state="readonly", values=self.STATUSES, width=18)
        self.status.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        ttk.Label(metadata, text="Confiance").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.confidence = ttk.Combobox(metadata, state="readonly", values=self.CONFIDENCES, width=18)
        self.confidence.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        self.score_label = ttk.Label(metadata, text="Complétude : —")
        self.score_label.grid(row=0, column=4, padx=10, pady=5, sticky="w")
        ttk.Label(metadata, text="Sources, une par ligne").grid(row=1, column=0, padx=5, pady=5, sticky="nw")
        self.sources = tk.Text(metadata, height=3, width=60)
        self.sources.grid(row=1, column=1, columnspan=4, padx=5, pady=5, sticky="ew")
        ttk.Label(metadata, text="Notes de révision").grid(row=2, column=0, padx=5, pady=5, sticky="nw")
        self.notes = tk.Text(metadata, height=3, width=60)
        self.notes.grid(row=2, column=1, columnspan=4, padx=5, pady=5, sticky="ew")
        metadata.columnconfigure(4, weight=1)

        editor_frame = ttk.LabelFrame(self, text=" Fiche JSON révisée ")
        editor_frame.pack(fill="both", expand=True, padx=12, pady=5)
        self.editor = tk.Text(editor_frame, wrap="none", undo=True)
        ybar = ttk.Scrollbar(editor_frame, orient="vertical", command=self.editor.yview)
        xbar = ttk.Scrollbar(editor_frame, orient="horizontal", command=self.editor.xview)
        self.editor.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.editor.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        editor_frame.rowconfigure(0, weight=1)
        editor_frame.columnconfigure(0, weight=1)

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=12, pady=(5, 12))
        ttk.Button(actions, text="Valider la structure", command=self.validate_current).pack(side="left", padx=3)
        ttk.Button(actions, text="Enregistrer la révision", command=self.save_current, style="Accent.TButton").pack(side="left", padx=3)
        ttk.Button(actions, text="Recharger le catalogue", command=self.reload_catalogue).pack(side="left", padx=3)
        self.summary = ttk.Label(actions, text="")
        self.summary.pack(side="right", padx=5)

    def _refresh_species(self) -> None:
        query = self.search_var.get().casefold().strip()
        self.filtered = [profile for profile in self.catalogue if query in (scientific_name(profile) + " " + str(profile.get("nom_vern", ""))).casefold()]
        self.combo["values"] = [f"{scientific_name(profile)} — {profile['id']}" for profile in self.filtered]
        if self.filtered:
            self.combo.current(0)
            self.load_selected()
        summary = self.database.review_summary()
        self.summary.configure(text=" | ".join(f"{key}: {value}" for key, value in sorted(summary.items())) or "Aucune révision")

    def _profile(self) -> dict[str, Any] | None:
        index = self.combo.current()
        return self.filtered[index] if 0 <= index < len(self.filtered) else None

    def load_selected(self) -> None:
        profile = self._profile()
        if not profile:
            return
        review = self.database.get_catalog_review(profile["id"]) or {}
        data = review.get("override") or profile
        self.status.set(review.get("status", data.get("metadata", {}).get("review_status", "a_verifier")))
        self.confidence.set(review.get("confidence", data.get("metadata", {}).get("confidence", "non_renseignee")))
        self.sources.delete("1.0", tk.END)
        self.sources.insert("1.0", "\n".join(review.get("sources") or data.get("metadata", {}).get("sources", [])))
        self.notes.delete("1.0", tk.END)
        self.notes.insert("1.0", review.get("notes", ""))
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))
        self.score_label.configure(text=f"Complétude : {catalogue_review_score(data)} %")

    def _parsed(self) -> dict[str, Any]:
        value = json.loads(self.editor.get("1.0", tk.END))
        if not isinstance(value, dict):
            raise ValueError("La fiche doit être un objet JSON.")
        profile = self._profile()
        if profile:
            value["id"] = profile["id"]
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        metadata.update(
            {
                "sources": [line.strip() for line in self.sources.get("1.0", tk.END).splitlines() if line.strip()],
                "confidence": self.confidence.get() or "non_renseignee",
                "review_status": self.status.get() or "a_verifier",
                "last_reviewed": date.today().isoformat() if self.status.get() == "valide" else metadata.get("last_reviewed"),
            }
        )
        value["metadata"] = metadata
        return value

    def validate_current(self) -> bool:
        try:
            profile = self._parsed()
            errors, warnings = validate_profile(profile)
        except (json.JSONDecodeError, ValueError) as exc:
            messagebox.showerror("Validation", str(exc))
            return False
        if errors:
            messagebox.showerror("Validation", "\n".join(errors))
            return False
        messagebox.showinfo("Validation", "Structure valide." + ("\n\nAvertissements :\n" + "\n".join(warnings) if warnings else ""))
        return True

    def save_current(self) -> None:
        try:
            profile = self._parsed()
            errors, warnings = validate_profile(profile)
            if errors:
                raise ValueError("; ".join(errors))
            path = save_override(profile)
            self.database.save_catalog_review(
                species_id=profile["id"],
                status=self.status.get() or "brouillon",
                confidence=self.confidence.get() or "non_renseignee",
                sources=profile["metadata"]["sources"],
                notes=self.notes.get("1.0", tk.END).strip(),
                override=profile,
            )
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            messagebox.showerror("Révision", str(exc))
            return
        self.score_label.configure(text=f"Complétude : {catalogue_review_score(profile)} %")
        messagebox.showinfo("Révision", f"Révision enregistrée dans {path}." + ("\nAvertissements : " + "; ".join(warnings) if warnings else ""))
        self._refresh_species()

    def reload_catalogue(self) -> None:
        if self.reload_catalogue_callback:
            self.reload_catalogue_callback()
        messagebox.showinfo("Catalogue", "Les surcharges ont été rechargées. Certains onglets peuvent nécessiter un rafraîchissement.")
