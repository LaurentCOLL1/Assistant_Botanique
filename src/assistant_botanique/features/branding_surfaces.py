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
    ttk.Label(content, text="Développé par Laurent COLL1", justify="center").pack(pady=(0, 14))
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


def _install_maintenance_branding() -> None:
    from assistant_botanique.ui.maintenance_tab import MaintenanceTab

    if getattr(MaintenanceTab, "_branding_header_installed", False):
        return

    previous_build_ui = MaintenanceTab._build_ui

    def enhanced_build_ui(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", padx=12, pady=(10, 0))

        text = ttk.Frame(header)
        text.pack(side="left", fill="both", expand=True, anchor="nw", padx=(4, 20), pady=(10, 0))
        ttk.Label(text, text="Données & système", font=("TkDefaultFont", 17, "bold")).pack(anchor="w")
        ttk.Label(
            text,
            text=(
                "Sauvegardes, échanges de données, notifications, mises à jour et maintenance "
                "de votre installation Assistant Botanique."
            ),
            justify="left",
            wraplength=760,
        ).pack(anchor="w", pady=(7, 0))

        try:
            photo = load_brand_photo(self, size=180)
            brand = ttk.Label(header, image=photo)
            brand.image = photo
            brand.pack(side="right", anchor="ne", padx=(8, 4))
            self._assistant_botanique_maintenance_image = photo
        except (OSError, ValueError, tk.TclError):
            LOGGER.exception("Impossible d'afficher le visuel dans Données & système")

        previous_build_ui(self)

    MaintenanceTab._build_ui = enhanced_build_ui
    MaintenanceTab._branding_header_installed = True


def install_branding_surfaces() -> None:
    """Installe le visuel dans Données & système et la fenêtre À propos."""
    _install_about_menu()
    _install_maintenance_branding()


__all__ = ["install_branding_surfaces"]
