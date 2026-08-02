from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from assistant_botanique.features.collection_photo_viewer import (
    fit_photo_size,
    install_collection_photo_viewer,
)


def test_fit_photo_size_preserves_ratio_and_viewport() -> None:
    assert fit_photo_size(4000, 3000, 1000, 700) == (933, 700)
    assert fit_photo_size(3000, 4000, 700, 1000) == (700, 933)


def test_fit_photo_size_does_not_upscale_small_photo() -> None:
    assert fit_photo_size(320, 240, 1600, 1200) == (320, 240)


def test_fit_photo_size_rejects_invalid_dimensions() -> None:
    with pytest.raises(ValueError):
        fit_photo_size(0, 240, 800, 600)


def test_collection_photo_viewer_patch_replaces_preview_renderer(monkeypatch) -> None:
    class FakeTabGestion:
        def _render_collection_photos(self) -> None:
            raise AssertionError("ancien rendu")

    monkeypatch.setitem(sys.modules, "tab_gestion", SimpleNamespace(TabGestion=FakeTabGestion))

    install_collection_photo_viewer()

    assert FakeTabGestion._collection_photo_viewer_installed is True
    assert FakeTabGestion._render_collection_photos.__name__ == "render_photos"
    assert FakeTabGestion._open_collection_photo.__name__ == "open_photo"
