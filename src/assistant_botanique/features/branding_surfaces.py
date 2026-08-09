"""Déploie l'identité visuelle dans l'interface, au-delà de l'icône de fenêtre."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from assistant_botanique import __version__
from assistant_botanique.ui.app_icon import apply_app_icon, load_brand_photo

LOGGER = logging.getLogger(__name__)


def _display_version() -> str:
    version = __version__
    if "b" in version:
        base, beta = version.rsplit("b", 1)
        if beta.isdigit():
            return f"{base} Beta {beta}"
    return version


def _show_about(app) -> None:
    window = tk.Toplevel(app.root)
    window.title("À propos d’Assistant Botanique")
    window.transient(app.root)
    window.resizable(False, False)
    apply_app_icon(window)

    content = ttk.Frame(window, padding=22)
    content.pack(fill="both", expand=True)

    try:
        photo = load_brand_photo(window, size=240)
        image = ttk.Label(content, image=photo)
        image.image = photo
        image.pack(pady=(0, 12))
        window._assistant_botanique_about_image = photo
    except (OSError, ValueError, tk.TclError):
        LOGGER.exception("Impossible d'afficher le visuel dans la fenêtre À propos")

    ttk.Label(content, text="Assistant Botanique", font=("TkDefaultFont", 18, "bold")).pack()
    ttk.Label(content, text=f"Version {_display_version()}", font=("TkDefaultFont", 11)).pack(pady=(4, 10))
    ttk.Label(
        content,
        text=(
            "Assistant de gestion et de suivi d’une collection de plantes : "
            "contrôles du substrat, soins, historique, catalogue et sauvegardes."
        ),
        justify="center",
        wraplength=430,
    ).pack(pady=(0, 6))
    ttk.Label(content, text="Développé par Laurent COLLIN", justify="center").pack(pady=(0, 14))
    ttk.Button(content, text="Fermer", command=window.destroy).pack()

    window.update_idletasks()
    x = app.root.winfo_rootx() + max(0, (app.root.winfo_width() - window.winfo_width()) // 2)
    y = app.root.winfo_rooty() + max(0, (app.root.winfo_height() - window.winfo_height()) // 2)
    window.geometry(f"+{x}+{y}")
    window.grab_set()
    window.focus_set()


def _install_about_menu() -> None:
    from assistant_botanique.ui.app import PlantCareApp

    if getattr(PlantCareApp, "_about_menu_installed", False):
        return

    previous_build_menu = PlantCareApp._build_menu

    def enhanced_build_menu(self) -> None:
        previous_build_menu(self)
        try:
            menu = self.root.nametowidget(self.root.cget("menu"))
            end = menu.index("end")
            if end is None:
                return
            for index in range(end + 1):
                if menu.type(index) != "cascade" or menu.entrycget(index, "label") != "Aide":
                    continue
                help_menu = self.root.nametowidget(menu.entrycget(index, "menu"))
                help_menu.add_separator()
                help_menu.add_command(
                    label="À propos d’Assistant Botanique",
                    command=lambda: _show_about(self),
                )
                break
        except (KeyError, tk.TclError):
            LOGGER.exception("Impossible d'ajouter l'entrée À propos au menu Aide")

    PlantCareApp._build_menu = enhanced_build_menu
    PlantCareApp._about_menu_installed = True


def _section_title(widget) -> str:
    try:
        return str(widget.cget("text")).strip()
    except tk.TclError:
        return ""


def _find_section(children, prefix: str):
    return next((widget for widget in children if _section_title(widget).startswith(prefix)), None)


def _install_maintenance_branding() -> None:
    from assistant_botanique.ui.maintenance_tab import MaintenanceTab

    if getattr(MaintenanceTab, "_branding_header_installed", False):
        return

    previous_build_ui = MaintenanceTab._build_ui

    def enhanced_build_ui(self) -> None:
        # Toutes les extensions (sauvegardes automatiques, mise à jour directe, etc.)
        # construisent d'abord leurs cadres normalement. On ne change ici que leur
        # disposition finale pour reproduire la maquette de Données & système.
        previous_build_ui(self)
        sections = list(self.winfo_children())

        backup = _find_section(sections, "Sauvegarde et restauration")
        exchange = _find_section(sections, "Export modifiable et réimportation")
        notifications = _find_section(sections, "Notifications natives")
        versions = _find_section(sections, "Versions et maintenance")
        automatic = _find_section(sections, "Sauvegardes automatiques")
        privacy = _find_section(sections, "Données et confidentialité")
        ordered = [backup, exchange, notifications, versions, automatic, privacy]

        for child in sections:
            try:
                child.pack_forget()
            except tk.TclError:
                pass

        header = ttk.Frame(self)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(16, 6))
        ttk.Label(header, text="Données & système", font=("TkDefaultFont", 17, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text=(
                "Sauvegardes, échanges de données, notifications, mises à jour et maintenance "
                "de votre installation Assistant Botanique."
            ),
            justify="left",
            wraplength=1000,
        ).pack(anchor="w", pady=(6, 0))

        if backup is not None:
            backup.grid(row=1, column=0, sticky="new", padx=(12, 8), pady=(5, 5))
        if exchange is not None:
            exchange.grid(row=2, column=0, sticky="new", padx=(12, 8), pady=5)

        brand_host = ttk.Frame(self, width=245, height=245)
        brand_host.grid(row=1, column=1, rowspan=2, sticky="ne", padx=(8, 18), pady=(2, 0))
        brand_host.grid_propagate(False)
        try:
            photo = load_brand_photo(self, size=230)
            brand = ttk.Label(brand_host, image=photo)
            brand.image = photo
            brand.place(relx=1.0, rely=0.0, anchor="ne")
            self._assistant_botanique_maintenance_image = photo
        except (OSError, ValueError, tk.TclError):
            LOGGER.exception("Impossible d'afficher le visuel dans Données & système")

        next_row = 3
        for section in (notifications, versions, automatic):
            if section is None:
                continue
            section.grid(row=next_row, column=0, columnspan=2, sticky="ew", padx=12, pady=5)
            next_row += 1

        if privacy is not None:
            privacy.grid(
                row=next_row,
                column=0,
                columnspan=2,
                sticky="nsew",
                padx=12,
                pady=(5, 12),
            )
            self.rowconfigure(next_row, weight=1)
            next_row += 1

        # Toute extension future non reconnue reste visible en pleine largeur.
        for child in sections:
            if child in ordered:
                continue
            child.grid(row=next_row, column=0, columnspan=2, sticky="ew", padx=12, pady=5)
            next_row += 1

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0, minsize=255)

    MaintenanceTab._build_ui = enhanced_build_ui
    MaintenanceTab._branding_header_installed = True


def install_branding_surfaces() -> None:
    """Installe le visuel dans Données & système et la fenêtre À propos."""
    _install_about_menu()
    _install_maintenance_branding()


__all__ = ["install_branding_surfaces"]
