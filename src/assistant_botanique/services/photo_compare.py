"""Génération d'une comparaison photographique locale et interactive."""
from __future__ import annotations

import html
from pathlib import Path
from typing import Mapping

from assistant_botanique.services.photos import PhotoService


class PhotoCompareService:
    def __init__(self, photos: PhotoService):
        self.photos = photos

    def generate_html(
        self,
        first: Mapping[str, object],
        second: Mapping[str, object],
        destination: Path | str,
        *,
        title: str = "Comparaison photographique",
    ) -> Path:
        left = self.photos.resolve_path(str(first.get("path") or "")).resolve()
        right = self.photos.resolve_path(str(second.get("path") or "")).resolve()
        if not left.is_file() or not right.is_file():
            raise FileNotFoundError("Une des photos sélectionnées est introuvable.")
        output = Path(destination)
        output.parent.mkdir(parents=True, exist_ok=True)
        left_label = str(first.get("taken_at") or first.get("caption") or "Avant")
        right_label = str(second.get("taken_at") or second.get("caption") or "Après")
        document = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font-family: system-ui,sans-serif; margin:0; padding:20px; background:#181a1b; color:#fff; }}
main {{ max-width:1100px; margin:auto; }}
.compare {{ position:relative; aspect-ratio:4/3; overflow:hidden; background:#000; border-radius:12px; }}
.compare img {{ position:absolute; inset:0; width:100%; height:100%; object-fit:contain; background:#000; }}
.after {{ clip-path:inset(0 0 0 50%); }}
.line {{ position:absolute; top:0; bottom:0; left:50%; width:3px; background:#fff; box-shadow:0 0 5px #000; pointer-events:none; }}
input[type=range] {{ width:100%; margin:18px 0; }}
.labels {{ display:flex; justify-content:space-between; gap:20px; }}
.side {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:24px; }}
.side img {{ width:100%; max-height:500px; object-fit:contain; background:#000; }}
</style></head><body><main>
<h1>{html.escape(title)}</h1>
<div class="labels"><strong>{html.escape(left_label)}</strong><strong>{html.escape(right_label)}</strong></div>
<div class="compare" id="compare">
<img src="{left.as_uri()}" alt="Première photo">
<img class="after" id="after" src="{right.as_uri()}" alt="Deuxième photo">
<div class="line" id="line"></div></div>
<input id="slider" type="range" min="0" max="100" value="50" aria-label="Position du comparateur">
<div class="side"><img src="{left.as_uri()}" alt="{html.escape(left_label)}"><img src="{right.as_uri()}" alt="{html.escape(right_label)}"></div>
<script>
const slider=document.getElementById('slider'), after=document.getElementById('after'), line=document.getElementById('line');
slider.addEventListener('input',()=>{{const value=slider.value;after.style.clipPath=`inset(0 0 0 ${{value}}%)`;line.style.left=`${{value}}%`;}});
</script></main></body></html>"""
        output.write_text(document, encoding="utf-8")
        return output.resolve()
