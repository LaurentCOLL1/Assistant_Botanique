"""Correctifs complémentaires pour le scan mobile et l'ergonomie de Collection."""
from __future__ import annotations

import html
import json
import re
import urllib.parse
from typing import Any

from tkinter import ttk

from assistant_botanique.features.inventory import INVENTORY_SUBCATEGORIES
from assistant_botanique.services.barcode_scanner import (
    MAX_BARCODE_IMAGE_BYTES,
    decode_barcode_image,
)


def rewrite_stock_page(
    page: str,
    auth_suffix: str,
    *,
    barcode: str = "",
    scan_error: str = "",
) -> str:
    """Remplace les scans concurrents par une seule capture envoyée au même serveur."""
    if barcode:
        status_text = (
            f"Code détecté : {barcode}. Complétez les informations du produit puis enregistrez-le."
        )
    elif scan_error:
        status_text = f"Lecture impossible : {scan_error}"
    else:
        status_text = (
            "Le téléphone ouvrira son appareil photo. Cadrez le code-barres de près, "
            "avec une bonne lumière et sans reflet."
        )

    scan_form = f"""
              <form method="post" action="/api/barcode{html.escape(auth_suffix, quote=True)}"
                    enctype="multipart/form-data" id="same-origin-barcode-form">
                <input id="same-origin-barcode-photo" name="photo" type="file"
                       accept="image/jpeg,image/png,image/webp,image/*"
                       capture="environment" hidden required>
                <label class="button" for="same-origin-barcode-photo">📷 Scanner le code-barres</label>
                <p id="same-origin-scan-status" class="muted">{html.escape(status_text)}</p>
              </form>
"""

    # Supprime la vidéo, le bouton historique, le champ de fichier visible/injecté
    # et le texte d'état associés aux deux anciennes méthodes concurrentes.
    scan_block = re.compile(
        r"\s*<video id=\"barcode-video\".*?"
        r"<p id=\"scan-status\" class=\"muted\"></p>\s*",
        re.DOTALL,
    )
    page, replacements = scan_block.subn("\n" + scan_form, page, count=1)
    if not replacements:
        marker = '<form method="post" action="/api/inventory'
        position = page.find(marker)
        if position >= 0:
            page = page[:position] + scan_form + page[position:]

    # Retire les scripts des anciens scanners. Ils utilisaient soit getUserMedia,
    # soit fetch vers un second port local, source du message « Failed to fetch ».
    page = re.sub(
        r"<script>\s*const subcategories = JSON\.parse\(.*?</script>",
        "",
        page,
        count=1,
        flags=re.DOTALL,
    )
    page = re.sub(
        r"<script>\s*\(\(\) => \{\s*const abOldButton.*?</script>",
        "",
        page,
        count=1,
        flags=re.DOTALL,
    )

    escaped_barcode = html.escape(str(barcode), quote=True)
    barcode_input = '<input id="barcode" name="barcode" inputmode="numeric" autocomplete="off">'
    page = page.replace(
        barcode_input,
        (
            '<input id="barcode" name="barcode" inputmode="numeric" '
            f'autocomplete="off" value="{escaped_barcode}">'
        ),
        1,
    )

    subcategories_json = json.dumps(INVENTORY_SUBCATEGORIES, ensure_ascii=False).replace(
        "</", "<\\/"
    )
    script = f"""
<script>
(() => {{
  const scanForm = document.getElementById('same-origin-barcode-form');
  const scanInput = document.getElementById('same-origin-barcode-photo');
  const scanStatus = document.getElementById('same-origin-scan-status');
  if (scanForm && scanInput) {{
    scanInput.addEventListener('change', () => {{
      if (!scanInput.files || !scanInput.files.length) return;
      scanStatus.textContent = 'Analyse de la photo sur cet ordinateur…';
      scanForm.submit();
    }});
  }}

  const subcategories = {subcategories_json};
  const category = document.getElementById('category');
  const subcategory = document.getElementById('subcategory');
  function refreshSubcategories() {{
    if (!category || !subcategory) return;
    subcategory.innerHTML = '';
    (subcategories[category.value] || subcategories['Autre'] || []).forEach(value => {{
      const option = document.createElement('option');
      option.value = value;
      option.textContent = value;
      subcategory.appendChild(option);
    }});
  }}
  if (category) category.addEventListener('change', refreshSubcategories);
  refreshSubcategories();
}})();
</script>
"""
    return page.replace("</body>", script + "</body>", 1)


def _patch_same_origin_barcode() -> None:
    from assistant_botanique.services.local_web import (
        LocalCompanionServer,
        _multipart_fields,
        _path_with_query,
    )

    if getattr(LocalCompanionServer, "_same_origin_barcode_installed", False):
        return

    previous_start = LocalCompanionServer.start
    previous_stock_page = LocalCompanionServer._stock_page

    def stock_page(
        self,
        auth_suffix: str,
        *,
        saved: bool = False,
        barcode: str = "",
        scan_error: str = "",
    ) -> str:
        page = previous_stock_page(self, auth_suffix, saved=saved)
        return rewrite_stock_page(
            page,
            auth_suffix,
            barcode=barcode,
            scan_error=scan_error,
        )

    def start(self, *args: Any, **kwargs: Any) -> str:
        url = previous_start(self, *args, **kwargs)

        # La version précédente lançait un deuxième serveur sur un port aléatoire.
        # Il est arrêté immédiatement : tout passe désormais par le port du compagnon.
        legacy_scanner = getattr(self, "barcode_decode_server", None)
        if legacy_scanner and legacy_scanner.running:
            legacy_scanner.stop()

        if not self.server:
            return url
        handler_class = self.server.RequestHandlerClass
        if getattr(handler_class, "_same_origin_barcode_installed", False):
            return url

        previous_get = handler_class.do_GET
        previous_post = handler_class.do_POST
        service = self

        def do_get(request) -> None:
            path = urllib.parse.urlsplit(request.path).path
            if path != "/stock":
                previous_get(request)
                return
            if not request._authorized():
                request._forbidden()
                return
            params = request._params()
            suffix = request._auth_suffix()
            request._send(
                service._stock_page(
                    suffix,
                    saved=(params.get("saved") or [""])[0] == "1",
                    barcode=(params.get("barcode") or [""])[0],
                    scan_error=(params.get("scan_error") or [""])[0],
                )
            )

        def do_post(request) -> None:
            path = urllib.parse.urlsplit(request.path).path
            if path != "/api/barcode":
                previous_post(request)
                return
            if not request._authorized():
                request._forbidden()
                return

            suffix = request._auth_suffix()
            declared = int(request.headers.get("Content-Length", "0") or 0)
            if declared <= 0 or declared > MAX_BARCODE_IMAGE_BYTES + 1_000_000:
                request._redirect(
                    _path_with_query(
                        "/stock",
                        suffix,
                        scan_error="Taille de photo invalide.",
                    )
                )
                return

            try:
                _fields, files = _multipart_fields(
                    request.headers.get("Content-Type", ""),
                    request.rfile.read(declared),
                )
                _filename, payload = files["photo"]
                result = decode_barcode_image(payload)
            except Exception as exc:  # noqa: BLE001
                request._redirect(
                    _path_with_query(
                        "/stock",
                        suffix,
                        scan_error=str(exc),
                    )
                )
                return

            request._redirect(
                _path_with_query(
                    "/stock",
                    suffix,
                    barcode=result["text"],
                )
            )

        handler_class.do_GET = do_get
        handler_class.do_POST = do_post
        handler_class._same_origin_barcode_installed = True
        return url

    LocalCompanionServer._stock_page = stock_page
    LocalCompanionServer.start = start
    LocalCompanionServer._same_origin_barcode_installed = True


def _patch_collection_details() -> None:
    from tab_gestion import TabGestion

    if getattr(TabGestion, "_adjustable_collection_details_installed", False):
        return

    previous_init = TabGestion.__init__

    def enhanced_init(self, *args: Any, **kwargs: Any) -> None:
        previous_init(self, *args, **kwargs)
        details = self.txt_details.master
        photo_frame = getattr(self, "photo_preview_frame", None)
        self._collection_photos_visible = True
        self._details_drag_start_y = 0
        self._details_drag_start_height = int(self.txt_details.cget("height"))

        resize_handle = ttk.Label(
            details,
            text="↕ Faire glisser pour ajuster la hauteur des détails",
            anchor="center",
            cursor="sb_v_double_arrow",
        )
        if photo_frame is not None:
            resize_handle.pack(
                fill="x",
                padx=6,
                pady=(4, 0),
                before=photo_frame,
            )
        else:
            resize_handle.pack(fill="x", padx=6, pady=(4, 0), before=self.txt_details)

        toolbar = ttk.Frame(details)
        if photo_frame is not None:
            toolbar.pack(fill="x", padx=6, pady=(4, 0), before=photo_frame)
        else:
            toolbar.pack(fill="x", padx=6, pady=(4, 0), before=self.txt_details)
        self.collection_photo_toggle_button = ttk.Button(
            toolbar,
            text="Masquer les dernières photos",
            command=self._toggle_collection_photos,
        )
        self.collection_photo_toggle_button.pack(side="left")
        ttk.Label(
            toolbar,
            text="La molette et la barre à droite permettent de parcourir l'historique.",
        ).pack(side="left", padx=10)

        self.txt_details.pack_forget()
        self.collection_details_scrollbar = ttk.Scrollbar(
            details,
            orient="vertical",
            command=self.txt_details.yview,
        )
        self.txt_details.configure(yscrollcommand=self.collection_details_scrollbar.set)
        self.collection_details_scrollbar.pack(
            side="right",
            fill="y",
            padx=(0, 6),
            pady=(4, 6),
        )
        self.txt_details.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(6, 0),
            pady=(4, 6),
        )

        def begin_resize(event) -> None:
            self._details_drag_start_y = event.y_root
            self._details_drag_start_height = int(self.txt_details.cget("height"))

        def resize(event) -> None:
            delta_rows = round((self._details_drag_start_y - event.y_root) / 18)
            new_height = max(4, min(32, self._details_drag_start_height + delta_rows))
            self.txt_details.configure(height=new_height)
            details.update_idletasks()

        def reset_height(_event=None) -> None:
            self.txt_details.configure(height=9)
            details.update_idletasks()

        resize_handle.bind("<ButtonPress-1>", begin_resize)
        resize_handle.bind("<B1-Motion>", resize)
        resize_handle.bind("<Double-Button-1>", reset_height)
        self.collection_details_resize_handle = resize_handle

    def toggle_photos(self) -> None:
        frame = getattr(self, "photo_preview_frame", None)
        if frame is None:
            return
        if self._collection_photos_visible:
            frame.pack_forget()
            self._collection_photos_visible = False
            self.collection_photo_toggle_button.configure(text="Afficher les dernières photos")
            return
        frame.pack(
            fill="x",
            padx=6,
            pady=(6, 0),
            before=self.txt_details,
        )
        self._collection_photos_visible = True
        self.collection_photo_toggle_button.configure(text="Masquer les dernières photos")
        self._render_collection_photos()

    TabGestion.__init__ = enhanced_init
    TabGestion._toggle_collection_photos = toggle_photos
    TabGestion._adjustable_collection_details_installed = True


def install_followup_fixes() -> None:
    """Installe les correctifs après les intégrations d'ergonomie précédentes."""
    _patch_same_origin_barcode()
    _patch_collection_details()


__all__ = ["install_followup_fixes", "rewrite_stock_page"]
