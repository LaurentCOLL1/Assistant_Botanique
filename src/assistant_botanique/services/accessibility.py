"""Réglages d'accessibilité applicables à l'interface Tkinter."""
from __future__ import annotations

import tkinter as tk
from tkinter import font, ttk
from typing import Any, Mapping

DEFAULT_ACCESSIBILITY = {
    "text_scale": 1.0,
    "high_contrast": False,
    "reduce_motion": False,
    "focus_highlight": True,
}


def normalized_accessibility(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = settings.get("accessibility", {}) if isinstance(settings, Mapping) else {}
    try:
        scale = float(raw.get("text_scale", 1.0))
    except (TypeError, ValueError):
        scale = 1.0
    return {
        "text_scale": max(0.85, min(scale, 1.75)),
        "high_contrast": bool(raw.get("high_contrast", False)),
        "reduce_motion": bool(raw.get("reduce_motion", False)),
        "focus_highlight": bool(raw.get("focus_highlight", True)),
    }


class AccessibilityManager:
    @staticmethod
    def apply(root: tk.Misc, settings: Mapping[str, Any] | None) -> dict[str, Any]:
        config = normalized_accessibility(settings)
        scale = float(config["text_scale"])
        try:
            root.tk.call("tk", "scaling", max(1.0, scale * 1.3333))
        except tk.TclError:
            pass
        for name in (
            "TkDefaultFont",
            "TkTextFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkCaptionFont",
            "TkSmallCaptionFont",
            "TkIconFont",
            "TkTooltipFont",
        ):
            try:
                named = font.nametofont(name, root=root)
                base = int(named.cget("size") or 9)
                reference = int(named.actual().get("size") or base)
                if not hasattr(root, "_assistant_botanique_font_bases"):
                    root._assistant_botanique_font_bases = {}  # type: ignore[attr-defined]
                bases = root._assistant_botanique_font_bases  # type: ignore[attr-defined]
                if name not in bases:
                    bases[name] = abs(reference) or abs(base) or 9
                named.configure(size=max(8, round(bases[name] * scale)))
            except (tk.TclError, KeyError):
                continue

        style = ttk.Style(root)
        if config["focus_highlight"]:
            style.configure("TButton", padding=(8, 5))
            style.map("TButton", relief=[("focus", "solid")])
        if config["high_contrast"]:
            style.configure("HighContrast.TFrame", background="#000000")
            style.configure("HighContrast.TLabel", background="#000000", foreground="#ffffff")
            style.configure("TNotebook.Tab", padding=(12, 8))
            try:
                root.option_add("*selectBackground", "#ffd400")
                root.option_add("*selectForeground", "#000000")
                root.option_add("*highlightColor", "#ffd400")
            except tk.TclError:
                pass
        return config
