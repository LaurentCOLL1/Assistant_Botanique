"""Onglet de sauvegarde, échange de données, notifications et mises à jour."""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
import webbrowser
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from assistant_botanique.infrastructure.backup_config import BackupConfigRepository
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.infrastructure.settings import SettingsRepository
from assistant_botanique.services.backup import BackupService
from assistant_botanique.services.exchange import ExchangeService
from assistant_botanique.services.notifications import NotificationService
from assistant_botanique.services.planner import CarePlanner
from assistant_botanique.services.updater import check_for_update


class MaintenanceTab(ttk.Frame):
    def __init__(
        self,
        parent,
        database: Database,
        settings_repo: SettingsRepository,
        settings: dict[str, Any],
        on_data_changed: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self.database = database
        self.settings_repo = settings_repo
        self.settings = settings
        self.on_data_changed = on_data_changed
        self.backups = BackupService(database)
        self.exchange = ExchangeService(database)
        self.backup_config = BackupConfigRepository()
        self.backup_config.ensure_exists()
        self.notifications = NotificationService()
        self._build_ui()
        self.refresh_stats()

    def _build_ui(self) -> None:
        backup = ttk.LabelFrame(self, text=" Sauvegarde et restauration ")
        backup.pack(fill="x", padx=12, pady=(10, 5))
        ttk.Label(
            backup,
            text="Une archive .botanique contient la base SQLite, les photos, les réglages et les révisions du catalogue.",
            wraplength=1000,
        ).pack(anchor="w", padx=8, pady=(6, 2))
        ttk.Label(backup, text=f"Fichier modifiable : {self.backup_config.path}", wraplength=1000).pack(anchor="w", padx=8, pady=(0, 6))
        row = ttk.Frame(backup)
        row.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(row, text="Créer une sauvegarde complète", command=self.create_backup, style="Accent.TButton").pack(side="left", padx=3)
        ttk.Button(row, text="Restaurer une sauvegarde", command=self.restore_backup).pack(side="left", padx=3)
        ttk.Button(row, text="Ouvrir sauvegarde.ini", command=self.open_backup_config).pack(side="left", padx=3)

        exchange = ttk.LabelFrame(self, text=" Export modifiable et réimportation ")
        exchange.pack(fill="x", padx=12, pady=5)
        ttk.Label(
            exchange,
            text=(
                "JSON conserve l'historique et les tâches planifiées. CSV est plus simple à modifier dans un tableur ; "
                "lors d'une fusion, l'historique existant est conservé. Une sauvegarde de sécurité est créée avant import."
            ),
            wraplength=1000,
            justify="left",
        ).pack(anchor="w", padx=8, pady=(6, 3))
        exchange_row = ttk.Frame(exchange)
        exchange_row.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(exchange_row, text="Exporter en JSON", command=self.export_json).pack(side="left", padx=3)
        ttk.Button(exchange_row, text="Exporter en CSV", command=self.export_csv).pack(side="left", padx=3)
        ttk.Button(exchange_row, text="Prévisualiser et importer", command=self.import_data, style="Accent.TButton").pack(side="left", padx=3)

        notify = ttk.LabelFrame(self, text=" Notifications natives ")
        notify.pack(fill="x", padx=12, pady=5)
        ttk.Label(notify, text="Heure quotidienne (HH:MM)").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.time_var = tk.StringVar(value=self.settings.get("notifications", {}).get("time", "09:00"))
        ttk.Entry(notify, textvariable=self.time_var, width=10).grid(row=0, column=1, padx=5, pady=8, sticky="w")
        ttk.Button(notify, text="Tester", command=lambda: self.notifications.show("Assistant Botanique", "Notification de test réussie.")).grid(row=0, column=2, padx=5, pady=8)
        ttk.Button(notify, text="Installer la tâche Windows", command=self.install_task).grid(row=0, column=3, padx=5, pady=8)
        ttk.Button(notify, text="Retirer la tâche", command=self.remove_task).grid(row=0, column=4, padx=5, pady=8)
        if sys.platform != "win32":
            ttk.Label(
                notify,
                text="La tâche de fond automatique est proposée sous Windows ; les notifications dans l'application restent multiplateformes.",
            ).grid(row=1, column=0, columnspan=5, padx=8, pady=(0, 8), sticky="w")

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
            wraplength=1000,
            justify="left",
        ).pack(anchor="nw", padx=8, pady=8)

    def _configured_backup_directory(self) -> Path | None:
        try:
            return self.backup_config.load_directory()
        except ValueError as exc:
            messagebox.showerror("Configuration des sauvegardes", str(exc), parent=self)
            return None

    def open_backup_config(self) -> None:
        path = self.backup_config.ensure_exists()
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            messagebox.showerror("Configuration des sauvegardes", f"Impossible d'ouvrir le fichier :\n{path}\n\n{exc}", parent=self)

    def create_backup(self) -> None:
        directory = self._configured_backup_directory()
        if directory is None:
            return
        suggested = directory / f"assistant-botanique-{date.today():%Y%m%d}.botanique"
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
            messagebox.showerror("Sauvegarde", str(exc), parent=self)
            return
        messagebox.showinfo("Sauvegarde", f"Archive créée :\n{path}", parent=self)

    def restore_backup(self) -> None:
        directory = self._configured_backup_directory()
        if directory is None:
            return
        source = filedialog.askopenfilename(
            title="Restaurer une sauvegarde",
            initialdir=directory,
            filetypes=(("Sauvegarde Assistant Botanique", "*.botanique"),),
        )
        if not source:
            return
        if not messagebox.askyesno("Restauration", "Restaurer cette archive ? Une copie de sécurité des données actuelles sera conservée.", parent=self):
            return
        try:
            result = self.backups.restore(source)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Restauration", str(exc), parent=self)
            return
        messagebox.showinfo("Restauration", f"Restauration terminée. Redémarrez l'application.\nCopie de sécurité : {result['safety_copy']}", parent=self)

    def export_json(self) -> None:
        destination = filedialog.asksaveasfilename(
            title="Exporter la collection en JSON",
            defaultextension=".json",
            filetypes=(("Export JSON", "*.json"),),
        )
        if destination:
            try:
                path = self.exchange.export_json(destination)
            except (OSError, ValueError) as exc:
                messagebox.showerror("Export", str(exc), parent=self)
                return
            messagebox.showinfo("Export", f"Export JSON créé :\n{path}", parent=self)

    def export_csv(self) -> None:
        destination = filedialog.asksaveasfilename(
            title="Exporter la collection en CSV",
            defaultextension=".csv",
            filetypes=(("Export CSV", "*.csv"),),
        )
        if destination:
            try:
                path = self.exchange.export_csv(destination)
            except (OSError, ValueError) as exc:
                messagebox.showerror("Export", str(exc), parent=self)
                return
            messagebox.showinfo("Export", f"Export CSV créé :\n{path}", parent=self)

    def import_data(self) -> None:
        source = filedialog.askopenfilename(
            title="Importer une collection modifiée",
            filetypes=(("Exports modifiables", "*.json *.csv"), ("JSON", "*.json"), ("CSV", "*.csv")),
        )
        if not source:
            return
        try:
            preview = self.exchange.preview(source)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Import", str(exc), parent=self)
            return
        warning_text = "\n".join(f"• {item}" for item in preview.warnings)
        decision = messagebox.askyesnocancel(
            "Prévisualisation de l'import",
            (
                f"Fichier : {preview.path.name}\n"
                f"Plantes lues : {len(preview.plants)}\n"
                f"Nouvelles : {preview.new_count}\n"
                f"Existantes mises à jour : {preview.updated_count}\n\n"
                f"{warning_text}\n\n"
                "Oui : fusionner avec la collection actuelle\n"
                "Non : remplacer complètement la collection\n"
                "Annuler : ne rien modifier"
            ),
            parent=self,
        )
        if decision is None:
            return
        mode = "merge" if decision else "replace"
        directory = self._configured_backup_directory()
        if directory is None:
            return
        safety = directory / f"assistant-botanique-avant-import-{datetime.now():%Y%m%d-%H%M%S}.botanique"
        try:
            self.backups.create(safety)
            self.exchange.apply(preview, mode=mode)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Import", f"Import annulé : {exc}\n\nSauvegarde éventuelle : {safety}", parent=self)
            return
        if self.on_data_changed:
            self.on_data_changed()
        self.refresh_stats()
        messagebox.showinfo("Import", f"Import terminé en mode {mode}.\nSauvegarde de sécurité :\n{safety}", parent=self)

    def install_task(self) -> None:
        try:
            self.notifications.install_windows_task(self.time_var.get().strip())
            self.settings.setdefault("notifications", {})["time"] = self.time_var.get().strip()
            self.settings_repo.save(self.settings)
        except (OSError, RuntimeError, ValueError) as exc:
            messagebox.showerror("Notifications", str(exc), parent=self)
            return
        messagebox.showinfo("Notifications", "Tâche planifiée installée.", parent=self)

    def remove_task(self) -> None:
        self.notifications.remove_windows_task()
        messagebox.showinfo("Notifications", "Tâche planifiée retirée si elle existait.", parent=self)

    def check_update(self) -> None:
        try:
            info = check_for_update()
        except Exception as exc:
            messagebox.showerror("Mise à jour", f"Vérification impossible : {exc}", parent=self)
            return
        if not info.published:
            messagebox.showinfo("Mise à jour", f"Aucune version publiée.\nVersion installée : {info.current}", parent=self)
        elif info.available:
            if messagebox.askyesno("Mise à jour", f"Version {info.latest} disponible (actuelle {info.current}). Ouvrir le téléchargement ?", parent=self):
                webbrowser.open(info.release_url)
        else:
            messagebox.showinfo("Mise à jour", f"Vous utilisez la dernière version publiée ({info.current}).", parent=self)

    def refresh_stats(self) -> None:
        stats = self.database.stats()
        pending_tasks = len(CarePlanner(self.database).list_tasks(status="pending"))
        self.stats_label.configure(
            text=(
                f"{stats['plants']} plantes · {stats['events']} soins · {stats['photos']} photos · "
                f"{pending_tasks} tâches · {stats['reviews']} révisions"
            )
        )
