"""Génération d'étiquettes imprimables avec QR codes."""
from __future__ import annotations

import base64
import html
import io
from pathlib import Path
from typing import Any, Mapping

from core import scientific_name


class LabelService:
    def qr_png(self, payload: str) -> bytes:
        try:
            import qrcode
        except ImportError as exc:
            raise RuntimeError("Le module qrcode est nécessaire pour générer les étiquettes.") from exc
        image = qrcode.make(payload)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def generate_printable_sheet(
        self,
        plants: list[dict[str, Any]],
        profiles_by_id: Mapping[str, Mapping[str, Any]],
        destination: Path | str,
        *,
        base_url: str | None = None,
        companion_token: str | None = None,
    ) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        cards = []
        for plant in plants:
            plant_id = str(plant.get("id") or "")
            if not plant_id:
                continue
            profile = profiles_by_id.get(str(plant.get("species_id") or ""), {})
            if base_url:
                url = f"{base_url.rstrip('/')}/plant/{plant_id}"
                if companion_token:
                    url += f"?token={companion_token}"
            else:
                url = f"assistant-botanique://plant/{plant_id}"
            encoded = base64.b64encode(self.qr_png(url)).decode("ascii")
            nickname = html.escape(str(plant.get("surnom") or "Plante"))
            species = html.escape(scientific_name(profile) if profile else str(plant.get("species_id") or ""))
            context = plant.get("contexte") if isinstance(plant.get("contexte"), dict) else {}
            location = html.escape(str(context.get("emplacement") or ""))
            cards.append(
                f"""
                <article class="label">
                  <img class="qr" src="data:image/png;base64,{encoded}" alt="QR code">
                  <div class="text">
                    <h2>{nickname}</h2>
                    <p class="species">{species}</p>
                    <p>{location}</p>
                    <small>{html.escape(plant_id)}</small>
                  </div>
                </article>
                """
            )
        document = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Étiquettes Assistant Botanique</title>
<style>
@page {{ size: A4; margin: 10mm; }}
body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 0; }}
.toolbar {{ margin: 0 0 12px; }}
.grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 8mm; }}
.label {{ border: 1px solid #777; border-radius: 8px; min-height: 48mm;
          padding: 5mm; display: flex; align-items: center; break-inside: avoid; }}
.qr {{ width: 34mm; height: 34mm; margin-right: 5mm; }}
h2 {{ font-size: 16pt; margin: 0 0 2mm; }}
p {{ margin: 1mm 0; }}
.species {{ font-style: italic; }}
small {{ color: #666; font-size: 7pt; }}
@media print {{ .toolbar {{ display: none; }} }}
</style>
</head>
<body>
<div class="toolbar"><button onclick="window.print()">Imprimer les étiquettes</button></div>
<div class="grid">{''.join(cards)}</div>
</body>
</html>
"""
        destination.write_text(document, encoding="utf-8")
        return destination
