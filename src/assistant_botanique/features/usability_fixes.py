"""Correctifs d'ergonomie : scan mobile, infestations, photos et mises à jour."""
from __future__ import annotations

import threading
import tkinter as tk
import unicodedata
import urllib.parse
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Iterable

from assistant_botanique import __version__
from assistant_botanique.services.barcode_scanner import (
    BarcodeDecodeServer,
    inject_barcode_fallback,
)
from assistant_botanique.services.updater import (
    UpdateInfo,
    check_for_update,
    download_and_launch_update,
)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value))
    return " ".join(
        "".join(character for character in decomposed if not unicodedata.combining(character))
        .casefold()
        .split()
    )


def normalized_photo_preview_count(value: object) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 2
    return max(2, min(12, count))


class SearchablePlantDialog(tk.Toplevel):
    """Sélecteur de plante avec recherche et liste déroulante filtrée."""

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        choices: Iterable[tuple[str, str]],
    ) -> None:
        super().__init__(parent.winfo_toplevel())
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.result: str | None = None
        self._all_choices = list(choices)
        self._visible_choices = list(self._all_choices)
        self._value_by_label = {label: value for label, value in self._all_choices}
        self.search_var = tk.StringVar()
        self.choice_var = tk.StringVar()

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Rechercher une plante").pack(anchor="w")
        search = ttk.Entry(frame, textvariable=self.search_var, width=58)
        search.pack(fill="x", pady=(4, 10))
        ttk.Label(frame, text="Plante").pack(anchor="w")
        self.combo = ttk.Combobox(
            frame,
            textvariable=self.choice_var,
            state="readonly",
            width=56,
        )
        self.combo.pack(fill="x", pady=(4, 12))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Annuler", command=self.destroy).pack(side="right")
        ttk.Button(
            buttons,
            text="Sélectionner",
            command=self._accept,
            style="Accent.TButton",
        ).pack(side="right", padx=6)

        self.search_var.trace_add("write", self._filter)
        self.combo.bind("<Return>", lambda _event: self._accept())
        self.bind("<Escape>", lambda _event: self.destroy())
        self._render()
        search.focus_set()
        self.grab_set()
        self.wait_window(self)

    def _filter(self, *_args: Any) -> None:
        terms = _normalize(self.search_var.get()).split()
        self._visible_choices = [
            item
            for item in self._all_choices
            if all(term in _normalize(item[0]) for term in terms)
        ]
        self._render()

    def _render(self) -> None:
        labels = [label for label, _value in self._visible_choices]
        self.combo.configure(values=labels)
        if self.choice_var.get() not in labels:
            self.choice_var.set(labels[0] if labels else "")

    def _accept(self) -> None:
        self.result = self._value_by_label.get(self.choice_var.get())
        if self.result:
            self.destroy()


def _walk_widgets(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from _walk_widgets(child)


def _patch_local_companion() -> None:
    from assistant_botanique.services.local_web import LocalCompanionServer

    if getattr(LocalCompanionServer, "_barcode_photo_fallback_installed", False):
        return
    original_start = LocalCompanionServer.start
    original_stop = LocalCompanionServer.stop
    original_stock_page = LocalCompanionServer._stock_page

    def start(self, *args: Any, **kwargs: Any) -> str:
        url = original_start(self, *args, **kwargs)
        scanner = getattr(self, "barcode_decode_server", None)
        if scanner is None:
            scanner = BarcodeDecodeServer()
            self.barcode_decode_server = scanner
        advertised_host = urllib.parse.urlsplit(self.base_url).hostname or "127.0.0.1"
        scanner.start(lan=self.host == "0.0.0.0", advertised_host=advertised_host)
        return url

    def stop(self) -> None:
        scanner = getattr(self, "barcode_decode_server", None)
        if scanner:
            scanner.stop()
        original_stop(self)

    def stock_page(self, auth_suffix: str, *, saved: bool = False) -> str:
        page = original_stock_page(self, auth_suffix, saved=saved)
        scanner = getattr(self, "barcode_decode_server", None)
        decode_url = scanner.access_url if scanner and scanner.running else ""
        return inject_barcode_fallback(page, decode_url)

    LocalCompanionServer.start = start
    LocalCompanionServer.stop = stop
    LocalCompanionServer._stock_page = stock_page
    LocalCompanionServer._barcode_photo_fallback_installed = True


def _plant_choices(tab, plants: Iterable[dict[str, Any]]) -> list[tuple[str, str]]:
    choices = []
    for plant in plants:
        identifier = str(plant.get("id") or "")
        label = f"{tab._plant_label(plant)} — {identifier[:8]}"
        choices.append((label, identifier))
    return sorted(choices, key=lambda item: _normalize(item[0]))


def _patch_intelligence_tab() -> None:
    from core import ValidationError
    from assistant_botanique.infrastructure.intelligence_repository import IntelligenceRepository
    from assistant_botanique.ui.collection_intelligence_tab import CollectionIntelligenceTab

    if getattr(CollectionIntelligenceTab, "_analysis_usability_installed", False):
        return

    def remove_plant_from_infestation(self, case_id: str, plant_id: str) -> None:
        with self.database.connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM infestation_plants WHERE case_id=? AND plant_id=?",
                (case_id, plant_id),
            ).fetchone()
            if not existing:
                raise ValidationError("Cette plante n'est pas associée à l'incident.")
            conn.execute(
                "DELETE FROM infestation_plants WHERE case_id=? AND plant_id=?",
                (case_id, plant_id),
            )

    IntelligenceRepository.remove_plant_from_infestation = remove_plant_from_infestation

    original_build_ui = CollectionIntelligenceTab._build_ui
    original_build_infestations = CollectionIntelligenceTab._build_infestations

    def build_ui(self) -> None:
        original_build_ui(self)
        for widget in _walk_widgets(self):
            if isinstance(widget, ttk.Label) and str(widget.cget("text")) == "Collection & analyse":
                widget.configure(text="Analyse avancée")
                break

    def build_infestations(self) -> None:
        original_build_infestations(self)
        tab = self.infestation_tree.master
        for widget in tab.winfo_children():
            if not isinstance(widget, ttk.Button):
                continue
            text = str(widget.cget("text"))
            if text == "Ajouter une observation":
                widget.grid_configure(column=3)
            elif text == "Clôturer":
                widget.grid_configure(column=4)
        ttk.Button(
            tab,
            text="Retirer une plante",
            command=self._remove_infestation_plant,
        ).grid(row=1, column=2, padx=5, pady=6)

    def add_infestation_plant(self) -> None:
        case = self._case()
        if not case:
            messagebox.showwarning("Infestation", "Sélectionnez un incident.", parent=self)
            return
        associated = {str(item.get("plant_id") or "") for item in case.get("plants", [])}
        available = [plant for plant in self.plants if str(plant.get("id") or "") not in associated]
        if not available:
            messagebox.showinfo(
                "Infestation",
                "Toutes les plantes de la collection sont déjà associées à cet incident.",
                parent=self,
            )
            return
        dialog = SearchablePlantDialog(
            self,
            "Ajouter une plante à l'incident",
            _plant_choices(self, available),
        )
        if not dialog.result:
            return
        exposed = messagebox.askyesno(
            "Rôle de la plante",
            "Cette plante est-elle seulement exposée, sans symptôme confirmé ?",
            parent=self,
        )
        try:
            self.repository.add_plant_to_infestation(
                case["id"],
                dialog.result,
                role="exposee" if exposed else "atteinte",
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Infestation", str(exc), parent=self)
            return
        self._refresh_infestations()

    def remove_infestation_plant(self) -> None:
        case = self._case()
        if not case:
            messagebox.showwarning("Infestation", "Sélectionnez un incident.", parent=self)
            return
        case_plants = case.get("plants", [])
        if not case_plants:
            messagebox.showinfo("Infestation", "Cet incident ne contient aucune plante.", parent=self)
            return
        choices = [
            (
                f"{item.get('nickname', 'Sans nom')} — {item.get('species_id', '')} — {str(item.get('plant_id', ''))[:8]}",
                str(item.get("plant_id") or ""),
            )
            for item in case_plants
        ]
        dialog = SearchablePlantDialog(self, "Retirer une plante de l'incident", choices)
        if not dialog.result:
            return
        nickname = next(
            (item.get("nickname", "cette plante") for item in case_plants if item.get("plant_id") == dialog.result),
            "cette plante",
        )
        if not messagebox.askyesno(
            "Retirer la plante",
            f"Retirer {nickname} de cet incident sans clôturer les autres plantes ?",
            parent=self,
        ):
            return
        try:
            self.repository.remove_plant_from_infestation(case["id"], dialog.result)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Infestation", str(exc), parent=self)
            return
        self._refresh_infestations()

    CollectionIntelligenceTab._build_ui = build_ui
    CollectionIntelligenceTab._build_infestations = build_infestations
    CollectionIntelligenceTab._add_infestation_plant = add_infestation_plant
    CollectionIntelligenceTab._remove_infestation_plant = remove_infestation_plant
    CollectionIntelligenceTab._analysis_usability_installed = True


def _patch_collection_photos() -> None:
    from PIL import Image, ImageOps, ImageTk, UnidentifiedImageError
    from assistant_botanique.infrastructure.settings import SettingsRepository
    from assistant_botanique.services.photos import PhotoService
    from tab_gestion import TabGestion

    if getattr(TabGestion, "_collection_photo_preview_installed", False):
        return
    original_init = TabGestion.__init__
    original_details = TabGestion.afficher_details_plante

    def enhanced_init(self, *args: Any, **kwargs: Any) -> None:
        self._photo_settings_repo = SettingsRepository()
        self._photo_service = None
        self._photo_images: list[Any] = []
        original_init(self, *args, **kwargs)
        self._photo_service = PhotoService(self.repository.database)
        self.photo_preview_frame = ttk.LabelFrame(self.txt_details.master, text=" Dernières photos ")
        self.photo_preview_frame.pack(
            fill="x",
            padx=6,
            pady=(6, 0),
            before=self.txt_details,
        )
        self._render_collection_photos()

    def render_photos(self) -> None:
        frame = getattr(self, "photo_preview_frame", None)
        service = getattr(self, "_photo_service", None)
        if frame is None or service is None:
            return
        for child in frame.winfo_children():
            child.destroy()
        self._photo_images = []
        selected = self.tree.selection()
        if len(selected) != 1:
            ttk.Label(frame, text="Sélectionnez une plante pour afficher ses photos.").grid(
                row=0,
                column=0,
                sticky="w",
                padx=6,
                pady=6,
            )
            return
        settings = self._photo_settings_repo.load()
        count = normalized_photo_preview_count(
            settings.get("collection", {}).get("photo_preview_count", 2)
        )
        photos = self.repository.database.list_photos(selected[0])[:count]
        if not photos:
            ttk.Label(frame, text="Aucune photo enregistrée pour cette plante.").grid(
                row=0,
                column=0,
                sticky="w",
                padx=6,
                pady=6,
            )
            return
        displayed = 0
        for item in photos:
            path = service.resolve_path(str(item.get("path") or ""))
            try:
                with Image.open(path) as opened:
                    image = ImageOps.exif_transpose(opened).convert("RGB")
                    image.thumbnail((210, 145))
                    photo_image = ImageTk.PhotoImage(image.copy())
            except (OSError, UnidentifiedImageError):
                continue
            self._photo_images.append(photo_image)
            caption = str(item.get("caption") or "").strip()
            taken_at = str(item.get("taken_at") or "")
            label_text = caption or taken_at or "Photo"
            label = ttk.Label(
                frame,
                image=photo_image,
                text=label_text,
                compound="top",
                anchor="center",
                wraplength=210,
            )
            label.grid(
                row=displayed // 4,
                column=displayed % 4,
                padx=6,
                pady=6,
                sticky="n",
            )
            displayed += 1
        if not displayed:
            ttk.Label(frame, text="Les fichiers photo sont introuvables ou illisibles.").grid(
                row=0,
                column=0,
                sticky="w",
                padx=6,
                pady=6,
            )

    def show_details(self, event: Any = None) -> None:
        original_details(self, event)
        self._render_collection_photos()

    TabGestion.__init__ = enhanced_init
    TabGestion._render_collection_photos = render_photos
    TabGestion.afficher_details_plante = show_details
    TabGestion._collection_photo_preview_installed = True


def _patch_maintenance() -> None:
    from assistant_botanique.ui.maintenance_tab import MaintenanceTab

    if getattr(MaintenanceTab, "_clear_update_flow_installed", False):
        return
    original_build = MaintenanceTab._build_ui

    def build(self) -> None:
        original_build(self)
        self.available_update_info: UpdateInfo | None = None
        check_button = None
        install_button = None
        auto_panel = None
        for widget in _walk_widgets(self):
            if isinstance(widget, ttk.LabelFrame):
                title = str(widget.cget("text"))
                if title.startswith(" Sauvegardes automatiques"):
                    auto_panel = widget
                    widget.configure(text=" Sauvegardes automatiques et affichage ")
            if isinstance(widget, ttk.Button):
                text = str(widget.cget("text"))
                if text == "Vérifier les mises à jour":
                    check_button = widget
                elif text == "Vérifier et installer":
                    install_button = widget
        self.check_update_button = check_button
        self.install_update_button = install_button
        if check_button is not None:
            check_button.configure(command=self.check_update)
        if install_button is not None:
            install_button.configure(
                text="Installer la mise à jour",
                command=self.install_update,
                state="disabled",
            )
        if auto_panel is not None:
            current = self.settings.get("collection", {}).get("photo_preview_count", 2)
            self.collection_photo_count_var = tk.IntVar(
                value=normalized_photo_preview_count(current)
            )
            ttk.Label(auto_panel, text="Photos affichées dans Collection").grid(
                row=2,
                column=0,
                columnspan=2,
                sticky="w",
                padx=8,
                pady=(4, 8),
            )
            ttk.Spinbox(
                auto_panel,
                textvariable=self.collection_photo_count_var,
                from_=2,
                to=12,
                width=8,
            ).grid(row=2, column=2, padx=6, pady=(4, 8))
            ttk.Button(
                auto_panel,
                text="Appliquer",
                command=self._save_collection_photo_count,
            ).grid(row=2, column=3, padx=6, pady=(4, 8))

    def save_photo_count(self) -> None:
        count = normalized_photo_preview_count(self.collection_photo_count_var.get())
        self.collection_photo_count_var.set(count)
        self.settings.setdefault("collection", {})["photo_preview_count"] = count
        self.settings_repo.save(self.settings)
        self.auto_tools_status.configure(
            text=f"Collection affichera les {count} dernières photos de la plante sélectionnée."
        )
        if self.on_data_changed:
            self.on_data_changed()

    def check_update_ui(self) -> None:
        self.auto_tools_status.configure(text="Vérification des mises à jour…")
        if self.install_update_button is not None:
            self.install_update_button.configure(state="disabled")

        def worker() -> None:
            try:
                info = check_for_update(timeout=10)
            except Exception as exc:  # noqa: BLE001
                error_text = str(exc)
                self.after(
                    0,
                    lambda value=error_text: messagebox.showerror(
                        "Mise à jour",
                        f"Vérification impossible : {value}",
                        parent=self,
                    ),
                )
                self.after(0, lambda: self.auto_tools_status.configure(text="Vérification échouée."))
                return

            def apply_result() -> None:
                self.available_update_info = info
                if not info.published:
                    self.auto_tools_status.configure(text="Aucune version publiée.")
                    messagebox.showinfo(
                        "Mise à jour",
                        f"Aucune version publiée. Version installée : {info.current}",
                        parent=self,
                    )
                    return
                if not info.available:
                    self.auto_tools_status.configure(text=f"Version {info.current} à jour.")
                    messagebox.showinfo(
                        "Mise à jour",
                        f"Vous utilisez la dernière version publiée ({info.current}).",
                        parent=self,
                    )
                    return
                if self.install_update_button is not None:
                    self.install_update_button.configure(state="normal")
                mode = "installable directement" if info.directly_installable else "disponible sur GitHub"
                self.auto_tools_status.configure(
                    text=f"Nouvelle version {info.latest} {mode} — version actuelle {info.current}."
                )
                messagebox.showinfo(
                    "Mise à jour disponible",
                    f"La version {info.latest} est disponible.\n"
                    f"Version installée : {info.current}.\n\n"
                    "Utilisez le bouton « Installer la mise à jour » pour continuer.",
                    parent=self,
                )

            self.after(0, apply_result)

        threading.Thread(
            target=worker,
            name="assistant-botanique-update-check",
            daemon=True,
        ).start()

    def install_update_ui(self) -> None:
        self.auto_tools_status.configure(text="Préparation de la mise à jour…")

        def worker() -> None:
            info = self.available_update_info
            try:
                if info is None or not info.available:
                    info = check_for_update(timeout=10)
            except Exception as exc:  # noqa: BLE001
                error_text = str(exc)
                self.after(
                    0,
                    lambda value=error_text: messagebox.showerror(
                        "Mise à jour",
                        f"Vérification impossible : {value}",
                        parent=self,
                    ),
                )
                return
            if not info.available:
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Mise à jour",
                        f"Aucune mise à jour à installer. Version actuelle : {info.current}.",
                        parent=self,
                    ),
                )
                self.after(0, lambda: self.auto_tools_status.configure(text=f"Version {info.current} à jour."))
                return
            self.available_update_info = info
            if not info.directly_installable:
                def open_release() -> None:
                    if messagebox.askyesno(
                        "Installer la mise à jour",
                        f"La version {info.latest} ne contient pas d'installateur direct compatible. "
                        "Ouvrir sa page de téléchargement ?",
                        parent=self,
                    ):
                        webbrowser.open(info.release_url)
                self.after(0, open_release)
                self.after(0, lambda: self.auto_tools_status.configure(text="Installateur direct indisponible."))
                return

            decision = threading.Event()
            accepted = {"value": False}

            def ask_permission() -> None:
                accepted["value"] = messagebox.askyesno(
                    "Installer la mise à jour",
                    f"Télécharger et lancer la version {info.latest} ?\n\n"
                    "L'application devra être fermée lorsque l'installateur le demandera.",
                    parent=self,
                )
                decision.set()

            self.after(0, ask_permission)
            decision.wait()
            if not accepted["value"]:
                self.after(0, lambda: self.auto_tools_status.configure(text="Installation annulée."))
                return

            try:
                def progress(downloaded: int, total: int) -> None:
                    text = f"Téléchargement : {downloaded / 1048576:.1f} Mo"
                    if total:
                        text += f" / {total / 1048576:.1f} Mo"
                    self.after(0, lambda value=text: self.auto_tools_status.configure(text=value))

                path = download_and_launch_update(info, progress=progress)
            except Exception as exc:  # noqa: BLE001
                error_text = str(exc)
                self.after(
                    0,
                    lambda value=error_text: messagebox.showerror(
                        "Mise à jour",
                        value,
                        parent=self,
                    ),
                )
                self.after(0, lambda: self.auto_tools_status.configure(text="Installation non lancée."))
                return
            self.after(
                0,
                lambda filename=Path(path).name: self.auto_tools_status.configure(
                    text=f"Installateur lancé : {filename}"
                ),
            )
            self.after(
                0,
                lambda: messagebox.showinfo(
                    "Mise à jour",
                    "L'installateur est lancé. Enregistrez votre travail puis fermez l'application lorsqu'il le demande.",
                    parent=self,
                ),
            )

        threading.Thread(
            target=worker,
            name="assistant-botanique-update-install",
            daemon=True,
        ).start()

    MaintenanceTab._build_ui = build
    MaintenanceTab._save_collection_photo_count = save_photo_count
    MaintenanceTab.check_update = check_update_ui
    MaintenanceTab.install_update = install_update_ui
    MaintenanceTab._clear_update_flow_installed = True


def _patch_app_labels() -> None:
    from assistant_botanique.ui.app import PlantCareApp

    if getattr(PlantCareApp, "_analysis_label_installed", False):
        return
    original_create_tabs = PlantCareApp._create_tabs
    original_apply_mode = PlantCareApp._apply_ui_mode

    def create_tabs(self) -> None:
        original_create_tabs(self)
        widget, _label = self.tabs_by_key["intelligence"]
        self.tabs_by_key["intelligence"] = (widget, "🧠 Analyse avancée")

    def apply_mode(self) -> None:
        original_apply_mode(self)
        suffix = "Mode simple" if self.ui_mode == "simple" else "Mode avancé"
        self.root.title(f"Assistant Botanique {__version__} — {suffix}")

    PlantCareApp._create_tabs = create_tabs
    PlantCareApp._apply_ui_mode = apply_mode
    PlantCareApp._analysis_label_installed = True


def install_usability_fixes() -> None:
    """Installe les correctifs avant la création de la fenêtre principale."""
    _patch_local_companion()
    _patch_intelligence_tab()
    _patch_collection_photos()
    _patch_maintenance()
    _patch_app_labels()
