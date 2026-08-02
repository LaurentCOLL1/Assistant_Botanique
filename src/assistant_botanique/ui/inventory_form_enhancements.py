"""Contrôles spécialisés du formulaire de stock et nettoyage des sorties Substrats."""
from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date
from tkinter import ttk
from typing import Callable, Iterable

from core import ValidationError, format_date_fr, parse_date

INVENTORY_CATEGORIES = (
    "Engrais",
    "Produit phytosanitaire",
    "Substrat",
    "Amendement",
    "Additif",
    "Paillage",
    "Pot et contenant",
    "Tuteur et support",
    "Outil",
    "Capteur",
    "Éclairage",
    "Irrigation",
    "Protection",
    "Consommable",
    "Autre",
)

INVENTORY_UNITS = (
    "unité",
    "pièce",
    "pot",
    "sac",
    "sachet",
    "boîte",
    "flacon",
    "dose",
    "g",
    "kg",
    "mL",
    "cL",
    "L",
    "cm",
    "m",
    "m²",
    "m³",
)

_INTERNAL_SUBSTRATE_LINES = {
    "Contrôle: les ingrédients proviennent exclusivement de la liste de l'onglet Substrats.",
}

MONTH_NAMES_FR = (
    "",
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre",
    "Octobre",
    "Novembre",
    "Décembre",
)
WEEKDAY_NAMES_FR = ("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim")


def merge_choice_values(standard_values: Iterable[str], current_value: str | None) -> tuple[str, ...]:
    """Ajoute une éventuelle ancienne valeur personnalisée sans créer de doublon."""
    values = list(dict.fromkeys(str(value) for value in standard_values if str(value).strip()))
    current = str(current_value or "").strip()
    if current and current not in values:
        values.append(current)
    return tuple(values)


def format_expiry_for_display(value: object) -> str:
    """Présente une date SQLite ISO dans le format français du formulaire."""
    if value in (None, ""):
        return ""
    try:
        return format_date_fr(parse_date(value))
    except (TypeError, ValueError, ValidationError):
        return str(value)


def remove_internal_substrate_lines(text: str) -> str:
    """Retire les messages de contrôle technique qui ne concernent pas l'utilisateur."""
    return "\n".join(line for line in str(text).splitlines() if line.strip() not in _INTERNAL_SUBSTRATE_LINES)


class DatePickerDialog(tk.Toplevel):
    """Petit calendrier modal sans dépendance externe."""

    def __init__(
        self,
        parent: tk.Misc,
        initial_value: object,
        on_select: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self.title("Choisir une date d'expiration")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.on_select = on_select
        try:
            selected = parse_date(initial_value) if initial_value else date.today()
        except (TypeError, ValueError, ValidationError):
            selected = date.today()
        self.year = selected.year
        self.month = selected.month
        self.selected = selected
        self.calendar = calendar.Calendar(firstweekday=calendar.MONDAY)

        self.header = ttk.Frame(self)
        self.header.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Button(self.header, text="◀", width=4, command=lambda: self._change_month(-1)).pack(side="left")
        self.month_label = ttk.Label(self.header, anchor="center", font=("Segoe UI", 10, "bold"))
        self.month_label.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(self.header, text="▶", width=4, command=lambda: self._change_month(1)).pack(side="right")

        self.days_frame = ttk.Frame(self)
        self.days_frame.pack(padx=8, pady=4)
        for column, label in enumerate(WEEKDAY_NAMES_FR):
            ttk.Label(self.days_frame, text=label, anchor="center", width=4).grid(
                row=0,
                column=column,
                padx=1,
                pady=(0, 3),
            )

        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=8, pady=(4, 8))
        ttk.Button(footer, text="Effacer", command=self._clear).pack(side="left")
        ttk.Button(footer, text="Aujourd'hui", command=self._today).pack(side="left", padx=5)
        ttk.Button(footer, text="Annuler", command=self.destroy).pack(side="right")

        self.bind("<Escape>", lambda _event: self.destroy())
        self._render_month()
        self.update_idletasks()
        self._center_over_parent(parent)
        self.grab_set()
        self.focus_set()

    def _center_over_parent(self, parent: tk.Misc) -> None:
        top = parent.winfo_toplevel()
        x = top.winfo_rootx() + max(0, (top.winfo_width() - self.winfo_reqwidth()) // 2)
        y = top.winfo_rooty() + max(0, (top.winfo_height() - self.winfo_reqheight()) // 2)
        self.geometry(f"+{x}+{y}")

    def _change_month(self, delta: int) -> None:
        absolute = self.year * 12 + (self.month - 1) + delta
        self.year, zero_based_month = divmod(absolute, 12)
        self.month = zero_based_month + 1
        self._render_month()

    def _render_month(self) -> None:
        self.month_label.configure(text=f"{MONTH_NAMES_FR[self.month]} {self.year}")
        for widget in self.days_frame.grid_slaves():
            if int(widget.grid_info().get("row", 0)) > 0:
                widget.destroy()
        weeks = self.calendar.monthdayscalendar(self.year, self.month)
        for row, week in enumerate(weeks, start=1):
            for column, day_number in enumerate(week):
                if day_number == 0:
                    ttk.Label(self.days_frame, text="", width=4).grid(row=row, column=column, padx=1, pady=1)
                    continue
                style = "Accent.TButton" if self.selected == date(self.year, self.month, day_number) else "TButton"
                ttk.Button(
                    self.days_frame,
                    text=str(day_number),
                    width=4,
                    style=style,
                    command=lambda day=day_number: self._choose(day),
                ).grid(row=row, column=column, padx=1, pady=1)

    def _choose(self, day_number: int) -> None:
        chosen = date(self.year, self.month, day_number)
        self.on_select(format_date_fr(chosen))
        self.destroy()

    def _today(self) -> None:
        self.on_select(format_date_fr(date.today()))
        self.destroy()

    def _clear(self) -> None:
        self.on_select("")
        self.destroy()


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
    self.inv_vars = {
        key: tk.StringVar()
        for key in ("name", "category", "unit", "quantity", "threshold", "expiry", "notes")
    }

    ttk.Label(form, text="Nom").grid(row=0, column=0, sticky="w", padx=6, pady=5)
    ttk.Entry(form, textvariable=self.inv_vars["name"]).grid(row=0, column=1, sticky="ew", padx=6, pady=5)

    ttk.Label(form, text="Catégorie").grid(row=1, column=0, sticky="w", padx=6, pady=5)
    self.inventory_category_combo = ttk.Combobox(
        form,
        textvariable=self.inv_vars["category"],
        values=INVENTORY_CATEGORIES,
        state="readonly",
    )
    self.inventory_category_combo.grid(row=1, column=1, sticky="ew", padx=6, pady=5)

    ttk.Label(form, text="Unité").grid(row=2, column=0, sticky="w", padx=6, pady=5)
    self.inventory_unit_combo = ttk.Combobox(
        form,
        textvariable=self.inv_vars["unit"],
        values=INVENTORY_UNITS,
        state="readonly",
    )
    self.inventory_unit_combo.grid(row=2, column=1, sticky="ew", padx=6, pady=5)

    ttk.Label(form, text="Quantité").grid(row=3, column=0, sticky="w", padx=6, pady=5)
    self.inventory_quantity_spinbox = ttk.Spinbox(
        form,
        textvariable=self.inv_vars["quantity"],
        from_=0,
        to=1_000_000_000,
        increment=0.1,
        width=16,
    )
    self.inventory_quantity_spinbox.grid(row=3, column=1, sticky="ew", padx=6, pady=5)

    ttk.Label(form, text="Seuil d'alerte").grid(row=4, column=0, sticky="w", padx=6, pady=5)
    self.inventory_threshold_spinbox = ttk.Spinbox(
        form,
        textvariable=self.inv_vars["threshold"],
        from_=0,
        to=1_000_000_000,
        increment=0.1,
        width=16,
    )
    self.inventory_threshold_spinbox.grid(row=4, column=1, sticky="ew", padx=6, pady=5)

    ttk.Label(form, text="Expiration").grid(row=5, column=0, sticky="w", padx=6, pady=5)
    expiry_row = ttk.Frame(form)
    expiry_row.grid(row=5, column=1, sticky="ew", padx=6, pady=5)
    expiry_row.columnconfigure(0, weight=1)
    self.inventory_expiry_entry = ttk.Entry(
        expiry_row,
        textvariable=self.inv_vars["expiry"],
        state="readonly",
    )
    self.inventory_expiry_entry.grid(row=0, column=0, sticky="ew")
    self.inventory_expiry_entry.bind("<Button-1>", lambda _event: self._open_inventory_expiry_calendar())
    ttk.Button(expiry_row, text="📅", width=4, command=self._open_inventory_expiry_calendar).grid(
        row=0,
        column=1,
        padx=(4, 0),
    )
    ttk.Button(expiry_row, text="Effacer", command=lambda: self.inv_vars["expiry"].set("")).grid(
        row=0,
        column=2,
        padx=(4, 0),
    )

    ttk.Label(form, text="Notes").grid(row=6, column=0, sticky="w", padx=6, pady=5)
    ttk.Entry(form, textvariable=self.inv_vars["notes"]).grid(row=6, column=1, sticky="ew", padx=6, pady=5)

    self.current_inventory_id = None
    ttk.Button(form, text="Nouveau", command=self._new_inventory_item).grid(row=7, column=0, padx=6, pady=8)
    ttk.Button(form, text="Enregistrer", command=self._save_inventory_item, style="Accent.TButton").grid(
        row=7,
        column=1,
        padx=6,
        pady=8,
    )
    ttk.Button(form, text="Entrée de stock", command=lambda: self._adjust_stock(True)).grid(
        row=8,
        column=0,
        padx=6,
        pady=5,
    )
    ttk.Button(form, text="Utilisation", command=lambda: self._adjust_stock(False)).grid(
        row=8,
        column=1,
        padx=6,
        pady=5,
    )
    self._new_inventory_item()


def _new_inventory_item(self) -> None:
    self.current_inventory_id = None
    for variable in self.inv_vars.values():
        variable.set("")
    self.inv_vars["category"].set(INVENTORY_CATEGORIES[0])
    self.inv_vars["unit"].set(INVENTORY_UNITS[0])
    self.inv_vars["quantity"].set("0")
    self.inv_vars["threshold"].set("0")
    if hasattr(self, "inventory_tree"):
        self.inventory_tree.selection_remove(self.inventory_tree.selection())


def _load_inventory_item(self, _event=None) -> None:
    selection = self.inventory_tree.selection()
    if not selection:
        return
    self.current_inventory_id = selection[0]
    item = next((row for row in self.repository.list_inventory() if row["id"] == selection[0]), None)
    if not item:
        return
    category = str(item.get("category") or "Autre")
    unit = str(item.get("unit") or "unité")
    self.inventory_category_combo.configure(values=merge_choice_values(INVENTORY_CATEGORIES, category))
    self.inventory_unit_combo.configure(values=merge_choice_values(INVENTORY_UNITS, unit))
    values = {
        "name": item["name"],
        "category": category,
        "unit": unit,
        "quantity": item["quantity"],
        "threshold": item["reorder_level"],
        "expiry": format_expiry_for_display(item.get("expires_on")),
        "notes": item.get("notes") or "",
    }
    for key, value in values.items():
        self.inv_vars[key].set(str(value))


def _open_inventory_expiry_calendar(self) -> None:
    if getattr(self, "_inventory_calendar", None) and self._inventory_calendar.winfo_exists():
        self._inventory_calendar.lift()
        return
    self._inventory_calendar = DatePickerDialog(
        self,
        self.inv_vars["expiry"].get(),
        self.inv_vars["expiry"].set,
    )


def _wrap_substrate_calculation(original):
    def wrapped(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        text = self.output.get("1.0", "end-1c")
        cleaned = remove_internal_substrate_lines(text)
        if cleaned != text:
            self.output.configure(state="normal")
            self.output.delete("1.0", tk.END)
            self.output.insert("1.0", cleaned)
            self.output.configure(state="disabled")
        return result

    return wrapped


def install_ui_enhancements() -> None:
    """Installe une seule fois les contrôles spécialisés avant la création de la fenêtre."""
    from tab_substrat import TabSubstrat
    from assistant_botanique.ui.advanced_ecosystem_tab import AdvancedEcosystemTab

    if getattr(AdvancedEcosystemTab, "_inventory_controls_installed", False):
        return

    AdvancedEcosystemTab._build_inventory_tab = _build_inventory_tab
    AdvancedEcosystemTab._new_inventory_item = _new_inventory_item
    AdvancedEcosystemTab._load_inventory_item = _load_inventory_item
    AdvancedEcosystemTab._open_inventory_expiry_calendar = _open_inventory_expiry_calendar
    AdvancedEcosystemTab._inventory_controls_installed = True

    if not getattr(TabSubstrat, "_recipe_output_cleaner_installed", False):
        TabSubstrat.calculer_recette = _wrap_substrate_calculation(TabSubstrat.calculer_recette)
        TabSubstrat._recipe_output_cleaner_installed = True
