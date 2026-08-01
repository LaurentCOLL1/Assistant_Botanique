"""Architecture d'extensions locales, chargées uniquement après activation explicite."""
from __future__ import annotations

import importlib.util
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from assistant_botanique.infrastructure.intelligence_repository import IntelligenceRepository
from assistant_botanique.paths import DATA_DIR

PLUGIN_API_VERSION = 1
PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


@dataclass(frozen=True, slots=True)
class PluginDescriptor:
    plugin_id: str
    name: str
    version: str
    description: str
    entrypoint: Path
    manifest_path: Path
    enabled: bool
    compatible: bool
    error: str = ""


class PluginAPI:
    """Surface volontairement réduite fournie aux extensions."""

    def __init__(self):
        self.importers: dict[str, Callable[..., Any]] = {}
        self.sensor_adapters: dict[str, Callable[..., Any]] = {}
        self.report_sections: dict[str, Callable[..., Any]] = {}

    def register_importer(self, name: str, callback: Callable[..., Any]) -> None:
        self.importers[str(name)] = callback

    def register_sensor_adapter(self, name: str, callback: Callable[..., Any]) -> None:
        self.sensor_adapters[str(name)] = callback

    def register_report_section(self, name: str, callback: Callable[..., Any]) -> None:
        self.report_sections[str(name)] = callback


class PluginManager:
    def __init__(
        self,
        repository: IntelligenceRepository,
        root: Path | str | None = None,
    ):
        self.repository = repository
        self.root = Path(root) if root else DATA_DIR / "plugins"
        self.root.mkdir(parents=True, exist_ok=True)
        self.loaded_modules: dict[str, ModuleType] = {}
        self.api = PluginAPI()

    def discover(self) -> list[PluginDescriptor]:
        descriptors = []
        for manifest_path in sorted(self.root.glob("*/plugin.json")):
            error = ""
            compatible = False
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                plugin_id = str(payload.get("id") or "").strip().casefold()
                if not PLUGIN_ID_RE.fullmatch(plugin_id):
                    raise ValueError("Identifiant d'extension invalide.")
                api_version = int(payload.get("api_version", 0))
                compatible = api_version == PLUGIN_API_VERSION
                entry_name = str(payload.get("entrypoint") or "plugin.py")
                entrypoint = (manifest_path.parent / entry_name).resolve()
                if entrypoint.parent != manifest_path.parent.resolve() or not entrypoint.is_file():
                    raise ValueError("Point d'entrée introuvable ou situé hors du dossier de l'extension.")
                state = self.repository.plugin_state(plugin_id)
                descriptors.append(
                    PluginDescriptor(
                        plugin_id=plugin_id,
                        name=str(payload.get("name") or plugin_id),
                        version=str(payload.get("version") or "0"),
                        description=str(payload.get("description") or ""),
                        entrypoint=entrypoint,
                        manifest_path=manifest_path,
                        enabled=bool(state.get("enabled")),
                        compatible=compatible,
                        error="" if compatible else f"API {api_version} non compatible",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                descriptors.append(
                    PluginDescriptor(
                        plugin_id=manifest_path.parent.name,
                        name=manifest_path.parent.name,
                        version="?",
                        description="",
                        entrypoint=manifest_path.parent / "plugin.py",
                        manifest_path=manifest_path,
                        enabled=False,
                        compatible=False,
                        error=str(exc),
                    )
                )
        return descriptors

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        self.repository.set_plugin_state(plugin_id, enabled=enabled)

    def load_enabled(self) -> dict[str, str]:
        results: dict[str, str] = {}
        for descriptor in self.discover():
            if not descriptor.enabled:
                results[descriptor.plugin_id] = "désactivée"
                continue
            if not descriptor.compatible:
                results[descriptor.plugin_id] = descriptor.error or "incompatible"
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"assistant_botanique_plugin_{descriptor.plugin_id.replace('.', '_')}",
                    descriptor.entrypoint,
                )
                if not spec or not spec.loader:
                    raise RuntimeError("Impossible de préparer l'extension.")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                register = getattr(module, "register", None)
                if not callable(register):
                    raise RuntimeError("L'extension doit exposer register(api).")
                register(self.api)
                self.loaded_modules[descriptor.plugin_id] = module
                results[descriptor.plugin_id] = "chargée"
            except Exception as exc:  # noqa: BLE001
                results[descriptor.plugin_id] = f"erreur : {exc}"
        return results
