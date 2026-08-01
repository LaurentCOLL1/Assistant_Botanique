"""Fenêtres d'appairage QR et de gestion des téléphones autorisés."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import qrcode
from PIL import ImageTk

from assistant_botanique.services.device_pairing import DevicePairingService
from assistant_botanique.services.local_web import LocalCompanionServer


def show_pairing_qr(parent: tk.Misc, companion: LocalCompanionServer) -> None:
    session = companion.create_pairing_session(ttl_seconds=300)
    window = tk.Toplevel(parent)
    window.title("Associer un téléphone")
    window.transient(parent)
    window.resizable(False, False)

    frame = ttk.Frame(window, padding=18)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Associer un téléphone", font=("Segoe UI", 17, "bold")).pack(pady=(0, 8))
    ttk.Label(
        frame,
        text=(
            "Connectez le téléphone au même Wi-Fi que l'ordinateur, puis scannez ce QR code. "
            "Le code est à usage unique et expire après cinq minutes."
        ),
        wraplength=460,
        justify="center",
    ).pack(pady=(0, 10))

    qr = qrcode.make(session.url).get_image().convert("RGB").resize((320, 320))
    image = ImageTk.PhotoImage(qr, master=window)
    qr_label = ttk.Label(frame, image=image)
    qr_label.image = image
    qr_label.pack(pady=6)

    url_var = tk.StringVar(value=session.url)
    entry = ttk.Entry(frame, textvariable=url_var, width=65, state="readonly")
    entry.pack(fill="x", pady=8)
    ttk.Label(
        frame,
        text=f"Expiration : {session.expires_at:%H:%M:%S}",
    ).pack()

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(12, 0))

    def copy_url() -> None:
        window.clipboard_clear()
        window.clipboard_append(session.url)
        messagebox.showinfo("Appairage", "Adresse copiée.", parent=window)

    ttk.Button(buttons, text="Copier l'adresse", command=copy_url).pack(side="left")
    ttk.Button(buttons, text="Fermer", command=window.destroy).pack(side="right")


def show_paired_devices(parent: tk.Misc, pairing: DevicePairingService) -> None:
    window = tk.Toplevel(parent)
    window.title("Téléphones associés")
    window.transient(parent)
    window.geometry("720x380")

    frame = ttk.Frame(window, padding=12)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Téléphones associés", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 8))
    ttk.Label(
        frame,
        text="Révoquer un téléphone coupe immédiatement son accès au prochain échange avec l'ordinateur.",
        wraplength=680,
    ).pack(anchor="w", pady=(0, 8))

    tree = ttk.Treeview(
        frame,
        columns=("name", "created", "last_seen"),
        show="headings",
        selectmode="browse",
    )
    for key, title, width in (
        ("name", "Appareil", 220),
        ("created", "Associé le", 180),
        ("last_seen", "Dernière connexion", 180),
    ):
        tree.heading(key, text=title)
        tree.column(key, width=width)
    tree.pack(fill="both", expand=True)

    def refresh() -> None:
        tree.delete(*tree.get_children())
        for device in pairing.list_devices():
            tree.insert(
                "",
                "end",
                iid=device["id"],
                values=(device["name"], device["created_at"], device.get("last_seen_at") or "—"),
            )

    def revoke() -> None:
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Téléphones", "Sélectionnez un appareil.", parent=window)
            return
        if not messagebox.askyesno(
            "Révoquer l'accès",
            "Ce téléphone devra scanner un nouveau QR code pour se reconnecter. Continuer ?",
            parent=window,
        ):
            return
        pairing.revoke(selection[0])
        refresh()

    controls = ttk.Frame(frame)
    controls.pack(fill="x", pady=(10, 0))
    ttk.Button(controls, text="Actualiser", command=refresh).pack(side="left")
    ttk.Button(controls, text="Révoquer l'appareil", command=revoke).pack(side="left", padx=8)
    ttk.Button(controls, text="Fermer", command=window.destroy).pack(side="right")
    refresh()
