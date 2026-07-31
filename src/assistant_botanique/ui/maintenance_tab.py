"""Onglet de sauvegarde, notifications et mises à jour."""
from __future__ import annotations

import sys
import tkinter as tk
import webbrowser
from datetime import date
from tkinter import filedialog, messagebox, ttk
from typing import Any

from assistant_botanique.infrastructure.database import Database
from assistant_botanique.infrastructure.settings import SettingsRepository
from assistant_botanique.paths import BACKUPS_DIR
from assistant_botanique.services.backup import BackupService
from assistant_botanique.services.notifications import NotificationService
from assistant_botanique.services.updater import check_for_update


class MaintenanceTab(ttk.Frame):
    def __init__(self, parent, database: Database, settings_repo: SettingsRepository, settings: dict[str, Any]):
        super().__init__(parent)
        self.database = database
        self.settings_repo = settings_repo
        self.settings = settings
        self.backups = BackupService(database)
        self.notifications = NotificationService()
        self._build_ui()
        self.refresh_stats()

    def _build_ui(self) -> None:
        backup = ttk.LabelFrame(self, text=" Sauvegarde et restauration ")
        backup.pack(fill="x", padx=12, pady=(10, 5))
        ttk.Label(
            backup,
            text="Une archive .botanique contient la base SQLite, les photos, les réglages et les révisions du catalogue.",
            wraplength=900,
        ).pack(anchor="w", padx=8, pady=6)
        row = ttk.Frame(backup)
        row.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(row, text="Créer une sauvegarde complète", command=self.create_backup, style="Accent.TButton").pack(side="left", padx=3)
        ttk.Button(row, text="Restaurer une sauvegarde", command=self.restore_backup).pack(side="left", padx=3)

        notify = ttk.LabelFrame(self, text=" Notifications natives ")
        notify.pack(fill="x", padx=12, pady=5)
        ttk.Label(notify, text="Heure quotidienne (HH:MM)").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.time_var = tk.StringVar(value=self.settings.get("notifications", {}).get("time", "09:00"))
        ttk.Entry(notify, textvariable=self.time_var, width=10).grid(row=0, column=1, padx=5, pady=8, sticky="w")
        ttk.Button(notify, text="Tester", command=lambda: self.notifications.show("Assistant Botanique", "Notification de test réussie.")).grid(row=0, column=2, padx=5, pady=8)
        ttk.Button(notify, text="Installer la tâche Windows", command=self.install_task).grid(row=0, column=3, padx=5, pady=8)
        ttk.Button(notify, text="Retirer la tâche", command=self.remove_task).grid(row=0, column=4, padx=5, pady=8)
        if sys.platform != "win32":
            ttk.Label(notify, text="La tâche de fond automatique est proposée sous Windows ; les notifications dans l'application restent multiplateformes.").grid(row=1, column=0, columnspan=5, padx=8, pady=(0, 8), sticky="w")

        update = ttk.LabelFrame(self, text=" Versions et maintenance ")
        update.pack(fill="x", padx=12, pady=5)
        ttk.Button(update, text="Vérifier les mises à jour", command=self.check_update).pack(side="left", padx=8, pady=8)
        ttk.Button(update, text="Actualiser les statistiques", command=self.refresh_stats).pack(side="left", padx=3, pady=8)
        self.stats_label = ttk.Label(update, text="")
        self.stats_label.pack(side="left", padx=12, pady=8)

        notes = ttk.LabelFrame(self, text=" Données et confidentialité ")
        notes.pack(fill="both", expand=True, padx=12, pady=(5, 12))
        ttk.Label(
            notes,
            text=(
                "Les données, photos et observations restent locales. La vérification de mise à jour contacte uniquement l'API publique "
                "des releases GitHub lorsqu'elle est déclenchée. Aucune photo n'est envoyée automatiquement."
            ),
            wraplength=950,
            justify="left",
        ).pack(anchor="nw", padx=8, pady=8)

    def create_backup(self) -> None:
        suggested = BACKUPS_DIR / f"assistant-botanique-{date.today():%Y%m%d}.botanique"
        destination = filedialog.asksaveasfilename(
            title="Créer une sauvegarde",
            initialdir=suggested.parent,
            initialfile=suggested.name,
            defaultextension=".botanique",
            filetypes=(("Sauvegarde Assistant Botanique", "*.botanique"),),
        )
        if not destination:
            return
        try:
            path = self.backups.create(destination)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Sauvegarde", str(exc))
            return
        messagebox.showinfo("Sauvegarde", f"Archive créée :\n{path}")

    def restore_backup(self) -> None:
        source = filedialog.askopenfilename(filetypes=(("Sauvegarde Assistant Botanique", "*.botanique"),))
        if not source:
            return
        if not messagebox.askyesno("Restauration", "Restaurer cette archive ? Une copie de sécurité des données actuelles sera conservée."):
            return
        try:
            result = self.backups.restore(source)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Restauration", str(exc))
            return
        messagebox.showinfo("Restauration", f"Restauration terminée. Redémarrez l'application.\nCopie de sécurité : {result['safety_copy']}")

    def install_task(self) -> None:
        try:
            self.notifications.install_windows_task(self.time_var.get().strip())
            self.settings.setdefault("notifications", {})["time"] = self.time_var.get().strip()
            self.settings_repo.save(self.settings)
        except (OSError, RuntimeError, ValueError) as exc:
            messagebox.showerror("Notifications", str(exc))
            return
        messagebox.showinfo("Notifications", "Tâche planifiée installée.")

    def remove_task(self) -> None:
        self.notifications.remove_windows_task()
        messagebox.showinfo("Notifications", "Tâche planifiée retirée si elle existait.")

    def check_update(self) -> None:
        try:
            info = check_for_update()
        except Exception as exc:
            messagebox.showerror("Mise à jour", f"Vérification impossible : {exc}")
            return
        if info.available:
            if messagebox.askyesno("Mise à jour", f"Version {info.latest} disponible (version actuelle {info.current}). Ouvrir la page de téléchargement ?"):
                webbrowser.open(info.release_url)
        else:
            messagebox.showinfo("Mise à jour", f"Vous utilisez la dernière version publiée ({info.current}).")

    def refresh_stats(self) -> None:
        stats = self.database.stats()
        self.stats_label.configure(text=f"{stats['plants']} plantes · {stats['events']} soins · {stats['photos']} photos · {stats['reviews']} révisions")
