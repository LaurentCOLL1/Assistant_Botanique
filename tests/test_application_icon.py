import base64
import io
from pathlib import Path

from PIL import Image

from assistant_botanique.ui.app_icon import ICON_RESOURCE, load_icon_base64
from tools.generate_app_icon import ICO_SIZES, generate_icons

ROOT = Path(__file__).resolve().parents[1]


def test_official_icon_source_is_a_valid_square_png():
    raw = base64.b64decode(load_icon_base64(), validate=True)
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")

    with Image.open(io.BytesIO(raw)) as image:
        assert image.size == (256, 256)
        assert image.width == image.height

    assert ICON_RESOURCE.as_posix() == "assets/app_icon.png.b64"


def test_icon_generator_creates_png_and_multiresolution_ico(tmp_path):
    png_path, ico_path = generate_icons(tmp_path)

    assert png_path.is_file()
    assert ico_path.is_file()
    with Image.open(png_path) as image:
        assert image.size == (256, 256)
    with Image.open(ico_path) as icon:
        available = set(icon.info.get("sizes", set()))
    assert {(size, size) for size in ICO_SIZES}.issubset(available)


def test_windows_build_and_installer_use_the_official_icon():
    builder = (ROOT / "tools" / "build_windows_installer.ps1").read_text(encoding="utf-8")
    installer = (ROOT / "installer" / "AssistantBotanique.iss").read_text(encoding="utf-8")

    assert "tools/generate_app_icon.py" in builder
    assert "--icon $GeneratedIcon" in builder
    assert '--add-data "assets;assets"' in builder
    assert "SetupIconFile=generated\\assistant_botanique.ico" in installer


def test_application_icon_is_installed_at_startup():
    feature_init = (ROOT / "src" / "assistant_botanique" / "features" / "__init__.py").read_text(encoding="utf-8")
    patch = (ROOT / "src" / "assistant_botanique" / "features" / "application_icon.py").read_text(encoding="utf-8")

    assert "install_application_icon()" in feature_init
    assert "apply_app_icon(root)" in patch
    assert "PlantCareApp.__init__ = enhanced_init" in patch


def test_branding_matches_the_maintenance_mockup_and_help_menu():
    feature_init = (ROOT / "src" / "assistant_botanique" / "features" / "__init__.py").read_text(encoding="utf-8")
    branding = (ROOT / "src" / "assistant_botanique" / "features" / "branding_surfaces.py").read_text(encoding="utf-8")
    icon_helpers = (ROOT / "src" / "assistant_botanique" / "ui" / "app_icon.py").read_text(encoding="utf-8")

    assert "install_branding_surfaces()" in feature_init
    assert 'text="Données & système"' in branding
    assert '_find_section(sections, "Sauvegarde et restauration")' in branding
    assert '_find_section(sections, "Export modifiable et réimportation")' in branding
    assert 'backup.grid(row=1, column=0' in branding
    assert 'exchange.grid(row=2, column=0' in branding
    assert 'brand_host.grid(row=1, column=1, rowspan=2' in branding
    assert "load_brand_photo(self, size=230)" in branding
    assert 'columnspan=2, sticky="ew"' in branding
    assert 'label="À propos d’Assistant Botanique"' in branding
    assert "load_brand_photo(window, size=240)" in branding
    assert 'text="Assistant Botanique"' in branding
    assert "Version {_display_version()}" in branding
    assert "load_brand_photo" in icon_helpers
