"""Intégration explicite des fonctions de productivité dans l'interface existante."""
from __future__ import annotations

import threading
import tkinter as tk
import unicodedata
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from assistant_botanique.features.backup_scheduler import BackupScheduler
from assistant_botanique.features.inventory import merge_choice_values, subcategories_for
from assistant_botanique.features.photo_diagnostic import analyze_photo, render_report_text
from assistant_botanique.features.repository import FeatureRepository
from assistant_botanique.services.updater import check_for_update, download_and_launch_update


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value))
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


class CommandPalette(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Palette de commandes")
        self.transient(app.root)
        self.geometry("660x430")
        self.minsize(520, 320)
        self.commands = self._commands()
        self.filtered = list(self.commands)
        self.query = tk.StringVar()
        entry = ttk.Entry(self, textvariable=self.query, font=("Segoe UI", 12))
        entry.pack(fill="x", padx=12, pady=(12, 6))
        self.listbox = tk.Listbox(self, activestyle="dotbox", font=("Segoe UI", 11))
        self.listbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.query.trace_add("write", self._filter)
        self.listbox.bind("<Double-Button-1>", self._run)
        self.listbox.bind("<Return>", self._run)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Down>", lambda _event: self._move(1))
        self.bind("<Up>", lambda _event: self._move(-1))
        self._render()
        entry.focus_set()
        self.grab_set()

    def _commands(self) -> list[tuple[str, Callable[[], None]]]:
        commands: list[tuple[str, Callable[[], None]]] = []
        for key, label in (
            ("today", "Ouvrir — Aujourd'hui"),
            ("collection", "Ouvrir — Collection"),
            ("search", "Ouvrir — Recherche globale"),
            ("calendar", "Ouvrir — Calendrier"),
            ("substrate", "Ouvrir — Substrats"),
            ("diagnostic", "Ouvrir — Diagnostic guidé"),
            ("ecosystem", "Ouvrir — Atelier avancé"),
            ("maintenance", "Ouvrir — Données et système"),
        ):
            if key in self.app.tabs_by_key:
                widget = self.app.tabs_by_key[key][0]
                commands.append((label, lambda target=widget: self.app.notebook.select(target)))
        commands.extend(
            (
                ("Afficher les contrôles du jour", self.app.show_due_items),
                ("Analyser une photo", lambda: show_photo_diagnostic(self.app)),
                ("Créer une sauvegarde maintenant", self._backup),
                ("Vérifier et installer une mise à jour", self._update),
                ("Associer un téléphone par QR code", self.app.pair_phone),
                ("Relancer l'assistant de première utilisation", lambda: FirstRunWizard(self.app, force=True)),
            )
        )
        return commands

    def _backup(self) -> None:
        result = self.app.backup_scheduler.run_now()
        if result.created:
            messagebox.showinfo("Sauvegarde", f"Sauvegarde créée :\n{result.path}", parent=self.app.root)
        else:
            messagebox.showerror("Sauvegarde", result.reason, parent=self.app.root)

    def _update(self) -> None:
        maintenance = getattr(self.app, "tab_maintenance", None)
        if maintenance:
            maintenance.check_update()

    def _filter(self, *_args) -> None:
        terms = _normalize(self.query.get()).split()
        self.filtered = [item for item in self.commands if all(term in _normalize(item[0]) for term in terms)]
        self._render()

    def _render(self) -> None:
        self.listbox.delete(0, tk.END)
        for label, _command in self.filtered:
            self.listbox.insert(tk.END, label)
        if self.filtered:
            self.listbox.selection_set(0)

    def _move(self, delta: int) -> str:
        if not self.filtered:
            return "break"
        selection = self.listbox.curselection()
        current = selection[0] if selection else 0
        target = max(0, min(len(self.filtered) - 1, current + delta))
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(target)
        self.listbox.see(target)
        return "break"

    def _run(self, _event=None) -> str:
        selection = self.listbox.curselection()
        if selection and selection[0] < len(self.filtered):
            _label, command = self.filtered[selection[0]]
            self.destroy()
            command()
        return "break"


class FirstRunWizard(tk.Toplevel):
    def __init__(self, app, *, force: bool = False):
        if not force and app.settings.get("onboarding", {}).get("completed"):
            return
        super().__init__(app.root)
        self.app = app
        self.title("Bienvenue dans Assistant Botanique")
        self.transient(app.root)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._close_without_finish)
        self.mode = tk.StringVar(value=app.ui_mode)
        self.notifications = tk.BooleanVar(value=bool(app.settings.get("notifications", {}).get("enabled", True)))
        automatic = app.settings.get("automatic_backups", {})
        self.backups = tk.BooleanVar(value=bool(automatic.get("enabled", True)))
        self.cadence = tk.StringVar(value=str(automatic.get("cadence") or "daily"))
        self.pages = ttk.Notebook(self)
        self.pages.pack(fill="both", expand=True, padx=12, pady=12)
        self._build_pages()
        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=12, pady=(0, 12))
        self.back = ttk.Button(footer, text="Précédent", command=self._previous)
        self.back.pack(side="left")
        self.next = ttk.Button(footer, text="Suivant", command=self._next, style="Accent.TButton")
        self.next.pack(side="right")
        self.pages.bind("<<NotebookTabChanged>>", lambda _event: self._update_buttons())
        self._update_buttons()
        self.update_idletasks()
        x = app.root.winfo_rootx() + max(0, (app.root.winfo_width() - self.winfo_reqwidth()) // 2)
        y = app.root.winfo_rooty() + max(0, (app.root.winfo_height() - self.winfo_reqheight()) // 2)
        self.geometry(f"+{x}+{y}")
        self.grab_set()

    def _build_pages(self) -> None:
        welcome = ttk.Frame(self.pages, padding=18)
        ttk.Label(welcome, text="Bienvenue", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            welcome,
            text="Cet assistant configure l'interface, les rappels et la protection de vos données. Tous les réglages pourront être modifiés plus tard.",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=12)
        self.pages.add(welcome, text="1. Bienvenue")

        interface = ttk.Frame(self.pages, padding=18)
        ttk.Label(interface, text="Mode d'interface", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Radiobutton(interface, text="Mode simple — fonctions essentielles", variable=self.mode, value="simple").pack(anchor="w", pady=6)
        ttk.Radiobutton(interface, text="Mode avancé — tous les outils", variable=self.mode, value="advanced").pack(anchor="w", pady=6)
        self.pages.add(interface, text="2. Interface")

        protection = ttk.Frame(self.pages, padding=18)
        ttk.Label(protection, text="Rappels et sauvegardes", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Checkbutton(protection, text="Activer les notifications de soins", variable=self.notifications).pack(anchor="w", pady=6)
        ttk.Checkbutton(protection, text="Créer des sauvegardes automatiques", variable=self.backups).pack(anchor="w", pady=6)
        row = ttk.Frame(protection)
        row.pack(anchor="w", pady=6)
        ttk.Label(row, text="Fréquence").pack(side="left")
        ttk.Combobox(row, textvariable=self.cadence, state="readonly", values=("daily", "weekly"), width=12).pack(side="left", padx=8)
        ttk.Label(
            protection,
            text="Le compagnon mobile fonctionne sur votre réseau local. Son activation réseau et l'association d'un téléphone restent toujours volontaires.",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(18, 0))
        self.pages.add(protection, text="3. Protection")

    def _index(self) -> int:
        return self.pages.index(self.pages.select())

    def _update_buttons(self) -> None:
        index = self._index()
        self.back.configure(state="disabled" if index == 0 else "normal")
        self.next.configure(text="Terminer" if index == self.pages.index("end") - 1 else "Suivant")

    def _previous(self) -> None:
        index = self._index()
        if index > 0:
            self.pages.select(index - 1)

    def _next(self) -> None:
        index = self._index()
        if index < self.pages.index("end") - 1:
            self.pages.select(index + 1)
            return
        self.app.settings.setdefault("notifications", {})["enabled"] = self.notifications.get()
        config = self.app.settings.setdefault("automatic_backups", {})
        config["enabled"] = self.backups.get()
        config["cadence"] = self.cadence.get()
        self.app.settings.setdefault("onboarding", {})["completed"] = True
        self.app.settings_repo.save(self.app.settings)
        self.app.set_ui_mode(self.mode.get())
        self.destroy()

    def _close_without_finish(self) -> None:
        self.app.settings.setdefault("onboarding", {})["dismissed"] = True
        self.app.settings_repo.save(self.app.settings)
        self.destroy()


def show_photo_diagnostic(app) -> None:
    source = filedialog.askopenfilename(
        title="Choisir une photo de la plante",
        filetypes=(("Images", "*.jpg *.jpeg *.png *.webp"),),
        parent=app.root,
    )
    if not source:
        return
    try:
        report = analyze_photo(Path(source))
        app.feature_repository.save_photo_diagnostic(
            plant_id=None,
            image_name=Path(source).name,
            summary=report.summary,
            report=report.as_dict(),
        )
    except Exception as exc:
        messagebox.showerror("Diagnostic photo", str(exc), parent=app.root)
        return
    window = tk.Toplevel(app.root)
    window.title("Diagnostic assisté par photo")
    window.geometry("760x560")
    text = tk.Text(window, wrap="word", padx=12, pady=12)
    text.pack(fill="both", expand=True)
    text.insert("1.0", render_report_text(report))
    text.configure(state="disabled")
    ttk.Button(window, text="Fermer", command=window.destroy).pack(pady=8)


def _install_app_patch() -> None:
    from assistant_botanique.ui.app import PlantCareApp

    if getattr(PlantCareApp, "_productivity_features_installed", False):
        return
    original_init = PlantCareApp.__init__

    def enhanced_init(self, root):
        original_init(self, root)
        self.feature_repository = FeatureRepository(self.database)
        self.backup_scheduler = BackupScheduler(self.database, self.settings, self.settings_repo)
        self.root.bind_all("<Control-Shift-P>", lambda _event: self.open_command_palette())
        self.root.bind_all("<Control-p>", lambda _event: self.open_command_palette())
        self._install_productivity_menu()
        self.root.after(700, lambda: self._run_automatic_backup(False))
        self.root.after(900, lambda: FirstRunWizard(self))

    def open_command_palette(self, _event=None):
        current = getattr(self, "_command_palette", None)
        if current and current.winfo_exists():
            current.lift()
        else:
            self._command_palette = CommandPalette(self)
        return "break"

    def install_menu(self):
        try:
            main_menu = self.root.nametowidget(self.root.cget("menu"))
        except (KeyError, tk.TclError):
            return
        menu = tk.Menu(main_menu, tearoff=False)
        menu.add_command(label="Palette de commandes", accelerator="Ctrl+Maj+P", command=self.open_command_palette)
        menu.add_command(label="Diagnostic assisté par photo", command=lambda: show_photo_diagnostic(self))
        menu.add_command(label="Assistant de première utilisation", command=lambda: FirstRunWizard(self, force=True))
        menu.add_separator()
        menu.add_command(label="Sauvegarde automatique maintenant", command=lambda: self._run_automatic_backup(True))
        main_menu.add_cascade(label="Productivité", menu=menu)

    def automatic_backup(self, show_result: bool = False):
        def worker():
            result = self.backup_scheduler.run_now() if show_result else self.backup_scheduler.run_if_due()
            if show_result:
                callback = messagebox.showinfo if result.created else messagebox.showerror
                title = "Sauvegarde"
                message = f"Sauvegarde créée :\n{result.path}" if result.created else result.reason
                self.root.after(0, lambda: callback(title, message, parent=self.root))
            self.root.after(60 * 60 * 1000, lambda: self._run_automatic_backup(False))

        threading.Thread(target=worker, name="assistant-botanique-auto-backup", daemon=True).start()

    PlantCareApp.__init__ = enhanced_init
    PlantCareApp.open_command_palette = open_command_palette
    PlantCareApp._install_productivity_menu = install_menu
    PlantCareApp._run_automatic_backup = automatic_backup
    PlantCareApp._productivity_features_installed = True


def _install_inventory_patch() -> None:
    from assistant_botanique.ui.advanced_ecosystem_tab import AdvancedEcosystemTab

    if getattr(AdvancedEcosystemTab, "_inventory_metadata_installed", False):
        return
    original_build = AdvancedEcosystemTab._build_inventory_tab
    original_new = AdvancedEcosystemTab._new_inventory_item
    original_load = AdvancedEcosystemTab._load_inventory_item
    original_save = AdvancedEcosystemTab._save_inventory_item

    def refresh_subcategories(self, *_args):
        category = self.inv_vars["category"].get()
        current = self.inv_vars["subcategory"].get()
        values = merge_choice_values(subcategories_for(category), current)
        self.inventory_subcategory_combo.configure(values=values)
        if current in values:
            self.inv_vars["subcategory"].set(current)
        elif values:
            self.inv_vars["subcategory"].set(values[0])

    def enhanced_build(self):
        original_build(self)
        form = self.inventory_category_combo.master
        for key in ("subcategory", "barcode", "brand"):
            self.inv_vars[key] = tk.StringVar()
        for widget in form.winfo_children():
            info = widget.grid_info()
            if info and int(info.get("row", 0)) >= 2:
                widget.grid_configure(row=int(info["row"]) + 3)
        ttk.Label(form, text="Sous-catégorie").grid(row=2, column=0, sticky="w", padx=6, pady=5)
        self.inventory_subcategory_combo = ttk.Combobox(form, textvariable=self.inv_vars["subcategory"], state="readonly")
        self.inventory_subcategory_combo.grid(row=2, column=1, sticky="ew", padx=6, pady=5)
        ttk.Label(form, text="Marque").grid(row=3, column=0, sticky="w", padx=6, pady=5)
        ttk.Entry(form, textvariable=self.inv_vars["brand"]).grid(row=3, column=1, sticky="ew", padx=6, pady=5)
        ttk.Label(form, text="Code-barres").grid(row=4, column=0, sticky="w", padx=6, pady=5)
        ttk.Entry(form, textvariable=self.inv_vars["barcode"]).grid(row=4, column=1, sticky="ew", padx=6, pady=5)
        self.inventory_category_combo.bind("<<ComboboxSelected>>", refresh_subcategories, add="+")
        self._feature_repository = FeatureRepository(self.database)
        refresh_subcategories(self)

    def enhanced_new(self):
        original_new(self)
        if hasattr(self, "inv_vars") and "subcategory" in self.inv_vars:
            self.inv_vars["barcode"].set("")
            self.inv_vars["brand"].set("")
            refresh_subcategories(self)

    def enhanced_load(self, event=None):
        original_load(self, event)
        if not self.current_inventory_id:
            return
        metadata = self._feature_repository.inventory_metadata(self.current_inventory_id)
        self.inv_vars["subcategory"].set(str(metadata.get("subcategory") or ""))
        self.inv_vars["barcode"].set(str(metadata.get("barcode") or ""))
        self.inv_vars["brand"].set(str(metadata.get("brand") or ""))
        refresh_subcategories(self)

    def enhanced_save(self):
        original_save(self)
        if not self.current_inventory_id:
            return
        try:
            self._feature_repository.save_inventory_metadata(
                self.current_inventory_id,
                category=self.inv_vars["category"].get(),
                subcategory=self.inv_vars["subcategory"].get(),
                barcode=self.inv_vars["barcode"].get(),
                brand=self.inv_vars["brand"].get(),
            )
        except Exception as exc:
            messagebox.showerror("Stock", str(exc), parent=self)

    AdvancedEcosystemTab._build_inventory_tab = enhanced_build
    AdvancedEcosystemTab._new_inventory_item = enhanced_new
    AdvancedEcosystemTab._load_inventory_item = enhanced_load
    AdvancedEcosystemTab._save_inventory_item = enhanced_save
    AdvancedEcosystemTab._refresh_inventory_subcategories = refresh_subcategories
    AdvancedEcosystemTab._inventory_metadata_installed = True


def _parse_recipe_text(value: str) -> dict[str, float]:
    ingredients: dict[str, float] = {}
    for raw_line in str(value).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        separator = "=" if "=" in line else ":" if ":" in line else None
        if not separator:
            raise ValueError(f"Ligne invalide : {line}. Utilisez Ingrédient = proportion.")
        name, raw_ratio = line.split(separator, 1)
        ingredients[name.strip()] = float(raw_ratio.strip().replace(",", ".").rstrip("%"))
    return ingredients


def _install_recipe_patch() -> None:
    from storage import CollectionRepository
    from tab_substrat import TabSubstrat

    if getattr(TabSubstrat, "_custom_recipes_installed", False):
        return
    original_build = TabSubstrat._build_ui

    def build(self):
        original_build(self)
        self._feature_repository = FeatureRepository(CollectionRepository().database)
        self.custom_recipe_by_label: dict[str, dict[str, Any]] = {}
        panel = ttk.LabelFrame(self.output.master, text=" Recettes personnelles ")
        panel.pack(fill="x", padx=8, pady=(2, 6), before=self.output)
        panel.columnconfigure(1, weight=1)
        self.custom_recipe_choice = ttk.Combobox(panel, state="readonly", width=30)
        self.custom_recipe_choice.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.custom_recipe_choice.bind("<<ComboboxSelected>>", lambda _event: self._load_custom_recipe())
        self.custom_recipe_name = tk.StringVar()
        ttk.Entry(panel, textvariable=self.custom_recipe_name).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.custom_recipe_description = tk.StringVar()
        ttk.Entry(panel, textvariable=self.custom_recipe_description).grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        self.custom_recipe_text = tk.Text(panel, height=4, wrap="none")
        self.custom_recipe_text.grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        self.custom_recipe_text.insert("1.0", "Fibre de coco = 50\nPerlite = 30\nÉcorces de pin = 20")
        buttons = ttk.Frame(panel)
        buttons.grid(row=0, column=2, rowspan=3, padx=5, pady=5, sticky="ns")
        ttk.Button(buttons, text="Enregistrer", command=self._save_custom_recipe).pack(fill="x", pady=2)
        ttk.Button(buttons, text="Appliquer", command=self._apply_custom_recipe, style="Accent.TButton").pack(fill="x", pady=2)
        ttk.Button(buttons, text="Supprimer", command=self._delete_custom_recipe).pack(fill="x", pady=2)
        ttk.Label(panel, text="Format : un ingrédient par ligne, par exemple Perlite = 30", style="Muted.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", padx=5, pady=(0, 5))
        self._refresh_custom_recipes()

    def refresh(self):
        recipes = self._feature_repository.list_recipes()
        self.custom_recipe_by_label = {item["name"]: item for item in recipes}
        self.custom_recipe_choice.configure(values=list(self.custom_recipe_by_label))

    def load(self):
        recipe = self.custom_recipe_by_label.get(self.custom_recipe_choice.get())
        if not recipe:
            return
        self.custom_recipe_name.set(recipe["name"])
        self.custom_recipe_description.set(recipe.get("description") or "")
        self.custom_recipe_text.delete("1.0", tk.END)
        self.custom_recipe_text.insert("1.0", "\n".join(f"{name} = {ratio * 100:g}" for name, ratio in recipe["ingredients"].items()))

    def save(self):
        try:
            ingredients = _parse_recipe_text(self.custom_recipe_text.get("1.0", "end-1c"))
            current = self.custom_recipe_by_label.get(self.custom_recipe_choice.get())
            identifier = self._feature_repository.save_recipe(
                recipe_id=current["id"] if current else None,
                name=self.custom_recipe_name.get(),
                ingredients=ingredients,
                description=self.custom_recipe_description.get(),
            )
        except Exception as exc:
            messagebox.showerror("Recette personnelle", str(exc), parent=self)
            return
        self._refresh_custom_recipes()
        for label, recipe in self.custom_recipe_by_label.items():
            if recipe["id"] == identifier:
                self.custom_recipe_choice.set(label)
                break

    def apply(self):
        try:
            ingredients = _parse_recipe_text(self.custom_recipe_text.get("1.0", "end-1c"))
            volume = float(self.entry_volume.get().replace(",", "."))
            if volume <= 0:
                raise ValueError("Le volume doit être positif.")
        except Exception as exc:
            messagebox.showerror("Recette personnelle", str(exc), parent=self)
            return
        total = sum(value for value in ingredients.values() if value > 0)
        if total <= 0:
            messagebox.showerror("Recette personnelle", "Ajoutez une proportion positive.", parent=self)
            return
        for name, variable in self.ing_vars.items():
            variable.set(name in ingredients)
        lines = ["=" * 72, f"RECETTE PERSONNELLE — {self.custom_recipe_name.get() or 'Sans nom'}", "=" * 72, ""]
        if self.custom_recipe_description.get().strip():
            lines.extend((self.custom_recipe_description.get().strip(), ""))
        for name, value in ingredients.items():
            ratio = value / total
            lines.append(f"• {name} — {ratio * 100:.1f}% = {volume * ratio:.3f} L")
        lines.extend(("", "Cette recette est personnelle et n'est pas une validation horticole automatique."))
        self.output.configure(state="normal")
        self.output.delete("1.0", tk.END)
        self.output.insert("1.0", "\n".join(lines))
        self.output.configure(state="disabled")

    def delete(self):
        recipe = self.custom_recipe_by_label.get(self.custom_recipe_choice.get())
        if not recipe:
            return
        if not messagebox.askyesno("Recette personnelle", f"Supprimer « {recipe['name']} » ?", parent=self):
            return
        self._feature_repository.delete_recipe(recipe["id"])
        self.custom_recipe_choice.set("")
        self._refresh_custom_recipes()

    TabSubstrat._build_ui = build
    TabSubstrat._refresh_custom_recipes = refresh
    TabSubstrat._load_custom_recipe = load
    TabSubstrat._save_custom_recipe = save
    TabSubstrat._apply_custom_recipe = apply
    TabSubstrat._delete_custom_recipe = delete
    TabSubstrat._custom_recipes_installed = True


def _install_maintenance_patch() -> None:
    from assistant_botanique.ui.maintenance_tab import MaintenanceTab

    if getattr(MaintenanceTab, "_automatic_tools_installed", False):
        return
    original_build = MaintenanceTab._build_ui

    def build(self):
        original_build(self)
        self.backup_scheduler = BackupScheduler(self.database, self.settings, self.settings_repo, backup_config=self.backup_config, service=self.backups)
        children = self.winfo_children()
        before = children[-1] if children else None
        panel = ttk.LabelFrame(self, text=" Sauvegardes automatiques et mise à jour directe ")
        pack_options = {"fill": "x", "padx": 12, "pady": 5}
        if before is not None:
            pack_options["before"] = before
        panel.pack(**pack_options)
        config = self.settings.setdefault("automatic_backups", {})
        self.auto_backup_enabled = tk.BooleanVar(value=bool(config.get("enabled", True)))
        self.auto_backup_cadence = tk.StringVar(value=str(config.get("cadence") or "daily"))
        self.auto_backup_retention = tk.IntVar(value=int(config.get("retention", 14)))
        ttk.Checkbutton(panel, text="Activer", variable=self.auto_backup_enabled, command=self._save_auto_backup_settings).grid(row=0, column=0, padx=6, pady=6)
        ttk.Combobox(panel, textvariable=self.auto_backup_cadence, state="readonly", values=("daily", "weekly"), width=12).grid(row=0, column=1, padx=6, pady=6)
        ttk.Spinbox(panel, textvariable=self.auto_backup_retention, from_=1, to=365, width=8).grid(row=0, column=2, padx=6, pady=6)
        ttk.Button(panel, text="Sauvegarder maintenant", command=self._run_auto_backup_now).grid(row=0, column=3, padx=6, pady=6)
        ttk.Button(panel, text="Vérifier et installer", command=self.check_update, style="Accent.TButton").grid(row=0, column=4, padx=6, pady=6)
        self.auto_tools_status = ttk.Label(panel, text=self.backup_scheduler.status_text(), wraplength=900)
        self.auto_tools_status.grid(row=1, column=0, columnspan=5, sticky="w", padx=8, pady=(0, 6))
        self.auto_backup_cadence.trace_add("write", lambda *_args: self._save_auto_backup_settings())
        self.auto_backup_retention.trace_add("write", lambda *_args: self._save_auto_backup_settings())

    def save_settings(self):
        config = self.settings.setdefault("automatic_backups", {})
        config["enabled"] = self.auto_backup_enabled.get()
        config["cadence"] = self.auto_backup_cadence.get()
        try:
            config["retention"] = max(1, min(365, int(self.auto_backup_retention.get())))
        except (tk.TclError, ValueError):
            config["retention"] = 14
        self.settings_repo.save(self.settings)

    def run_backup(self):
        self._save_auto_backup_settings()
        self.auto_tools_status.configure(text="Sauvegarde en cours…")

        def worker():
            result = self.backup_scheduler.run_now()
            text = f"Sauvegarde créée : {result.path}" if result.created else f"Échec : {result.reason}"
            self.after(0, lambda: self.auto_tools_status.configure(text=text))

        threading.Thread(target=worker, name="assistant-botanique-manual-auto-backup", daemon=True).start()

    def direct_update(self):
        self.auto_tools_status.configure(text="Recherche d'une mise à jour…")

        def worker():
            try:
                info = check_for_update(timeout=10)
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Mise à jour", str(exc), parent=self))
                self.after(0, lambda: self.auto_tools_status.configure(text="Vérification échouée."))
                return
            if not info.published:
                self.after(0, lambda: messagebox.showinfo("Mise à jour", info.notes, parent=self))
                self.after(0, lambda: self.auto_tools_status.configure(text="Aucune release publiée."))
                return
            if not info.available:
                self.after(0, lambda: messagebox.showinfo("Mise à jour", f"Version {info.current} déjà à jour.", parent=self))
                self.after(0, lambda: self.auto_tools_status.configure(text=f"Version installée : {info.current}"))
                return
            if not info.directly_installable:
                def fallback():
                    if messagebox.askyesno("Mise à jour", f"Version {info.latest} disponible, mais aucun installateur direct n'est attaché. Ouvrir la release ?", parent=self):
                        webbrowser.open(info.release_url)
                self.after(0, fallback)
                self.after(0, lambda: self.auto_tools_status.configure(text="Installateur direct indisponible."))
                return

            accepted = threading.Event()
            choice = {"value": False}

            def ask():
                choice["value"] = messagebox.askyesno(
                    "Installer la mise à jour",
                    f"Télécharger et lancer la version {info.latest} ?\n\nL'installateur vous guidera et l'application devra être fermée.",
                    parent=self,
                )
                accepted.set()

            self.after(0, ask)
            accepted.wait()
            if not choice["value"]:
                self.after(0, lambda: self.auto_tools_status.configure(text="Mise à jour annulée."))
                return
            try:
                def progress(downloaded: int, total: int):
                    text = f"Téléchargement : {downloaded / 1048576:.1f} Mo"
                    if total:
                        text += f" / {total / 1048576:.1f} Mo"
                    self.after(0, lambda value=text: self.auto_tools_status.configure(text=value))
                path = download_and_launch_update(info, progress=progress)
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Mise à jour", str(exc), parent=self))
                self.after(0, lambda: self.auto_tools_status.configure(text="Installation non lancée."))
                return
            self.after(0, lambda: self.auto_tools_status.configure(text=f"Installateur lancé : {path.name}"))
            self.after(0, lambda: messagebox.showinfo("Mise à jour", "L'installateur est lancé. Enregistrez votre travail puis fermez l'application lorsqu'il le demande.", parent=self))

        threading.Thread(target=worker, name="assistant-botanique-updater", daemon=True).start()

    MaintenanceTab._build_ui = build
    MaintenanceTab._save_auto_backup_settings = save_settings
    MaintenanceTab._run_auto_backup_now = run_backup
    MaintenanceTab.check_update = direct_update
    MaintenanceTab._automatic_tools_installed = True


def install_productivity_features() -> None:
    """Installe une seule fois les intégrations avant la création de la fenêtre."""
    _install_inventory_patch()
    _install_recipe_patch()
    _install_maintenance_patch()
    _install_app_patch()
