"""Thèmes visuels simples pour Tkinter/ttk."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

PALETTES = {
    "light": {
        "bg": "#f5f7f4", "panel": "#ffffff", "fg": "#1f2d24",
        "muted": "#52635a", "accent": "#2e7d4f", "field": "#ffffff",
        "select": "#d9efe1", "danger": "#b53636",
    },
    "dark": {
        "bg": "#1d2420", "panel": "#27302b", "fg": "#edf5ef",
        "muted": "#b8c6bd", "accent": "#63bd82", "field": "#313c36",
        "select": "#365743", "danger": "#ff7b7b",
    },
}


def apply_theme(root: tk.Misc, theme: str) -> None:
    palette = PALETTES.get(theme, PALETTES["light"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    root.configure(bg=palette["bg"])
    style.configure(".", background=palette["bg"], foreground=palette["fg"], font=("Segoe UI", 9))
    style.configure("TFrame", background=palette["bg"])
    style.configure("TLabel", background=palette["bg"], foreground=palette["fg"])
    style.configure("TLabelframe", background=palette["bg"], foreground=palette["fg"])
    style.configure("TLabelframe.Label", background=palette["bg"], foreground=palette["fg"], font=("Segoe UI", 9, "bold"))
    style.configure("TNotebook", background=palette["bg"])
    style.configure("TNotebook.Tab", padding=(10, 6), background=palette["panel"], foreground=palette["fg"])
    style.map("TNotebook.Tab", background=[("selected", palette["select"])])
    style.configure("Treeview", background=palette["field"], fieldbackground=palette["field"], foreground=palette["fg"], rowheight=25)
    style.configure("Treeview.Heading", background=palette["select"], foreground=palette["fg"], font=("Segoe UI", 9, "bold"))
    style.map("Treeview", background=[("selected", palette["select"])], foreground=[("selected", palette["fg"])])
    style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"))
    style.configure("Danger.TButton", foreground=palette["danger"], font=("Segoe UI", 9, "bold"))
    style.configure("Muted.TLabel", foreground=palette["muted"])
