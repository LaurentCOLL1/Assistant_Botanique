"""Décodage local de codes-barres photographiés depuis le compagnon mobile."""
from __future__ import annotations

import json
import secrets
import threading
import urllib.parse
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BARCODE_IMAGE_BYTES = 12 * 1024 * 1024
MAX_BARCODE_IMAGE_PIXELS = 50_000_000


def decode_barcode_image(payload: bytes) -> dict[str, str]:
    """Décode le premier code-barres lisible dans une image, entièrement en local."""
    if not payload:
        raise ValueError("La photo du code-barres est vide.")
    if len(payload) > MAX_BARCODE_IMAGE_BYTES:
        raise ValueError("La photo du code-barres dépasse la limite de 12 Mo.")
    try:
        import zxingcpp
    except ImportError as exc:  # pragma: no cover - dépend du paquet distribué
        raise RuntimeError("Le moteur de lecture de codes-barres n'est pas installé.") from exc

    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_BARCODE_IMAGE_PIXELS
    try:
        with Image.open(BytesIO(payload)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.thumbnail((4096, 4096))
            results = zxingcpp.read_barcodes(
                image,
                try_rotate=True,
                try_downscale=True,
                try_invert=True,
            )
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Le fichier reçu n'est pas une image valide ou sûre.") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit

    for result in results:
        text = str(getattr(result, "text", "") or "").strip()
        if text:
            return {
                "text": text,
                "format": str(getattr(result, "format", "") or "Code-barres"),
            }
    raise ValueError(
        "Aucun code-barres n'a été détecté. Reprenez la photo de près, bien éclairée et sans reflet."
    )


def _multipart_photo(content_type: str, body: bytes) -> bytes:
    if "multipart/form-data" not in content_type.casefold():
        raise ValueError("Formulaire de lecture invalide.")
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: "
        + content_type.encode("ascii", "ignore")
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + body
    )
    if not message.is_multipart():
        raise ValueError("Formulaire de lecture incomplet.")
    for part in message.iter_parts():
        if part.get_param("name", header="content-disposition") == "photo":
            return part.get_payload(decode=True) or b""
    raise ValueError("La photo du code-barres est absente.")


class BarcodeDecodeServer:
    """Petit endpoint local séparé, protégé par jeton, pour décoder une photo."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or secrets.token_urlsafe(24)
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.host = "127.0.0.1"
        self.port = 0
        self.advertised_host = "127.0.0.1"

    @property
    def running(self) -> bool:
        return bool(self.server and self.thread and self.thread.is_alive())

    @property
    def access_url(self) -> str:
        token = urllib.parse.quote(self.token)
        return f"http://{self.advertised_host}:{self.port}/decode?token={token}"

    def start(self, *, lan: bool, advertised_host: str) -> str:
        if self.running:
            return self.access_url
        self.host = "0.0.0.0" if lan else "127.0.0.1"
        self.advertised_host = advertised_host or "127.0.0.1"
        service = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "AssistantBotaniqueBarcode/1.0"

            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def _cors(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")

            def _json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
                raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self._cors()
                self.end_headers()
                self.wfile.write(raw)

            def do_OPTIONS(self) -> None:  # noqa: N802
                self.send_response(HTTPStatus.NO_CONTENT)
                self._cors()
                self.end_headers()

            def do_POST(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlsplit(self.path)
                supplied = (urllib.parse.parse_qs(parsed.query).get("token") or [""])[0]
                if parsed.path != "/decode" or not secrets.compare_digest(supplied, service.token):
                    self._json({"ok": False, "error": "Accès refusé."}, HTTPStatus.FORBIDDEN)
                    return
                declared = int(self.headers.get("Content-Length", "0") or 0)
                if declared <= 0 or declared > MAX_BARCODE_IMAGE_BYTES + 1_000_000:
                    self._json(
                        {"ok": False, "error": "Taille de formulaire invalide."},
                        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    )
                    return
                try:
                    photo = _multipart_photo(
                        self.headers.get("Content-Type", ""),
                        self.rfile.read(declared),
                    )
                    result = decode_barcode_image(photo)
                except Exception as exc:  # noqa: BLE001
                    self._json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                    return
                self._json({"ok": True, **result})

        self.server = ThreadingHTTPServer((self.host, 0), Handler)
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="assistant-botanique-barcode-server",
            daemon=True,
        )
        self.thread.start()
        return self.access_url

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        self.server = None
        self.thread = None


def inject_barcode_fallback(page: str, decode_url: str) -> str:
    """Ajoute une prise de photo fiable lorsque le scan vidéo n'est pas disponible."""
    marker = '<button type="button" id="scan-barcode">📷 Scanner le code-barres</button>'
    if marker not in page or not decode_url:
        return page
    replacement = marker + """
              <input id="barcode-photo" type="file" accept="image/*" capture="environment" hidden>
              <label class="button" for="barcode-photo">📸 Photographier le code-barres</label>"""
    page = page.replace(marker, replacement, 1)
    script = f"""
<script>
(() => {{
  const abOldButton = document.getElementById('scan-barcode');
  const abButton = abOldButton.cloneNode(true);
  abOldButton.replaceWith(abButton);
  const abPhoto = document.getElementById('barcode-photo');
  const abStatus = document.getElementById('scan-status');
  const abVideo = document.getElementById('barcode-video');
  const abBarcode = document.getElementById('barcode');
  const abDecodeUrl = {json.dumps(decode_url)};

  async function abDecodePhoto(file) {{
    if (!file) return;
    abStatus.textContent = 'Analyse de la photo sur l’ordinateur…';
    const form = new FormData();
    form.append('photo', file, file.name || 'code-barres.jpg');
    try {{
      const response = await fetch(abDecodeUrl, {{method: 'POST', body: form}});
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || 'Lecture impossible.');
      abBarcode.value = payload.text;
      abStatus.textContent = 'Code détecté : ' + payload.text;
      abBarcode.dispatchEvent(new Event('change', {{bubbles: true}}));
    }} catch (error) {{
      abStatus.textContent = 'Lecture impossible : ' + error.message;
    }}
  }}

  abPhoto.addEventListener('change', () => abDecodePhoto(abPhoto.files[0]));
  abButton.addEventListener('click', async () => {{
    abStatus.textContent = 'Ouverture du scanner…';
    const liveAvailable = window.isSecureContext
      && ('BarcodeDetector' in window)
      && navigator.mediaDevices
      && navigator.mediaDevices.getUserMedia;
    if (!liveAvailable) {{
      abStatus.textContent = 'Prenez une photo nette du code-barres.';
      abPhoto.value = '';
      abPhoto.click();
      return;
    }}
    let stream;
    try {{
      const detector = new BarcodeDetector({{formats:['ean_13','ean_8','upc_a','upc_e','code_128','code_39','itf']}});
      stream = await navigator.mediaDevices.getUserMedia({{video:{{facingMode:{{ideal:'environment'}}}}}});
      abVideo.srcObject = stream;
      abVideo.hidden = false;
      await abVideo.play();
      abStatus.textContent = 'Cadrez le code-barres…';
      const deadline = Date.now() + 20000;
      while (Date.now() < deadline) {{
        const results = await detector.detect(abVideo);
        if (results.length) {{
          abBarcode.value = results[0].rawValue;
          abStatus.textContent = 'Code détecté : ' + results[0].rawValue;
          return;
        }}
        await new Promise(resolve => setTimeout(resolve, 300));
      }}
      abStatus.textContent = 'Code non détecté. Utilisez le bouton Photographier.';
    }} catch (error) {{
      abStatus.textContent = 'Caméra directe indisponible. Utilisez le bouton Photographier.';
    }} finally {{
      if (stream) stream.getTracks().forEach(track => track.stop());
      abVideo.hidden = true;
    }}
  }});
}})();
</script>
"""
    return page.replace("</body>", script + "</body>", 1)
