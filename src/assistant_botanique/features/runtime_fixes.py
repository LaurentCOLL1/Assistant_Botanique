"""Correctifs de raccordement appliqués après l'intégration des fonctions."""
from __future__ import annotations

import threading
import webbrowser
from tkinter import messagebox

from assistant_botanique.services.updater import check_for_update, download_and_launch_update


def _install_safe_update_handler() -> None:
    from assistant_botanique.ui.maintenance_tab import MaintenanceTab

    def direct_update(self) -> None:
        self.auto_tools_status.configure(text="Recherche d'une mise à jour…")

        def worker() -> None:
            try:
                info = check_for_update(timeout=10)
            except Exception as exc:
                error_message = str(exc)
                self.after(
                    0,
                    lambda value=error_message: messagebox.showerror(
                        "Mise à jour",
                        value,
                        parent=self,
                    ),
                )
                self.after(0, lambda: self.auto_tools_status.configure(text="Vérification échouée."))
                return

            if not info.published:
                self.after(0, lambda: messagebox.showinfo("Mise à jour", info.notes, parent=self))
                self.after(0, lambda: self.auto_tools_status.configure(text="Aucune release publiée."))
                return
            if not info.available:
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Mise à jour",
                        f"Version {info.current} déjà à jour.",
                        parent=self,
                    ),
                )
                self.after(0, lambda: self.auto_tools_status.configure(text=f"Version installée : {info.current}"))
                return
            if not info.directly_installable:

                def fallback() -> None:
                    if messagebox.askyesno(
                        "Mise à jour",
                        f"Version {info.latest} disponible, mais aucun installateur direct n'est attaché. Ouvrir la release ?",
                        parent=self,
                    ):
                        webbrowser.open(info.release_url)

                self.after(0, fallback)
                self.after(0, lambda: self.auto_tools_status.configure(text="Installateur direct indisponible."))
                return

            accepted = threading.Event()
            choice = {"value": False}

            def ask() -> None:
                choice["value"] = messagebox.askyesno(
                    "Installer la mise à jour",
                    (
                        f"Télécharger et lancer la version {info.latest} ?\n\n"
                        "L'installateur vous guidera et l'application devra être fermée."
                    ),
                    parent=self,
                )
                accepted.set()

            self.after(0, ask)
            accepted.wait()
            if not choice["value"]:
                self.after(0, lambda: self.auto_tools_status.configure(text="Mise à jour annulée."))
                return

            try:

                def progress(downloaded: int, total: int) -> None:
                    text = f"Téléchargement : {downloaded / 1048576:.1f} Mo"
                    if total:
                        text += f" / {total / 1048576:.1f} Mo"
                    self.after(0, lambda value=text: self.auto_tools_status.configure(text=value))

                path = download_and_launch_update(info, progress=progress)
            except Exception as exc:
                error_message = str(exc)
                self.after(
                    0,
                    lambda value=error_message: messagebox.showerror(
                        "Mise à jour",
                        value,
                        parent=self,
                    ),
                )
                self.after(0, lambda: self.auto_tools_status.configure(text="Installation non lancée."))
                return

            self.after(0, lambda: self.auto_tools_status.configure(text=f"Installateur lancé : {path.name}"))
            self.after(
                0,
                lambda: messagebox.showinfo(
                    "Mise à jour",
                    (
                        "L'installateur est lancé. Enregistrez votre travail puis fermez "
                        "l'application lorsqu'il le demande."
                    ),
                    parent=self,
                ),
            )

        threading.Thread(target=worker, name="assistant-botanique-updater", daemon=True).start()

    MaintenanceTab.check_update = direct_update


def install_runtime_fixes() -> None:
    """Corrige les liaisons Tkinter et évite de créer une fenêtre d'accueil inutile."""
    from assistant_botanique.features import integration
    from assistant_botanique.ui.advanced_ecosystem_tab import AdvancedEcosystemTab

    if getattr(AdvancedEcosystemTab, "_productivity_runtime_fixes_installed", False):
        return

    current_build = AdvancedEcosystemTab._build_inventory_tab

    def build_inventory_with_safe_binding(self) -> None:
        current_build(self)
        combo = getattr(self, "inventory_category_combo", None)
        if combo is not None and hasattr(self, "_refresh_inventory_subcategories"):
            combo.bind(
                "<<ComboboxSelected>>",
                lambda _event: self._refresh_inventory_subcategories(),
            )

    AdvancedEcosystemTab._build_inventory_tab = build_inventory_with_safe_binding
    AdvancedEcosystemTab._productivity_runtime_fixes_installed = True

    original_wizard = integration.FirstRunWizard

    def guarded_wizard(app, *, force: bool = False):
        if not force and app.settings.get("onboarding", {}).get("completed"):
            return None
        return original_wizard(app, force=force)

    integration.FirstRunWizard = guarded_wizard
    _install_safe_update_handler()
