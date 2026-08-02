"""Compagnon web local, PWA, photos et stock par code-barres."""
from __future__ import annotations

import html
import json
import secrets
import socket
import threading
import urllib.parse
from datetime import date, datetime
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping

from assistant_botanique.features.inventory import INVENTORY_CATEGORIES, INVENTORY_SUBCATEGORIES, INVENTORY_UNITS
from assistant_botanique.features.photo_diagnostic import MAX_DIAGNOSTIC_BYTES, analyze_photo
from assistant_botanique.features.repository import FeatureRepository
from assistant_botanique.infrastructure.advanced_repository import AdvancedRepository
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.device_pairing import DevicePairingService, PairingSession
from assistant_botanique.services.photos import MAX_UPLOAD_BYTES, PhotoService
from assistant_botanique.services.planner import CarePlanner

ALLOWED_QUICK_ACTIONS = {
    "substrat_sec", "encore_humide", "arrosage", "fertilisation", "rempotage",
    "taille", "traitement", "observation",
}
DEVICE_COOKIE = "ab_device"


def _local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
        finally:
            sock.close()
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def _multipart_fields(content_type: str, body: bytes) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
    if "multipart/form-data" not in content_type.casefold():
        raise ValueError("Formulaire photo invalide.")
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("ascii", "ignore") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    )
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}
    if not message.is_multipart():
        raise ValueError("Formulaire photo incomplet.")
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename:
            files[str(name)] = (str(filename), payload)
        else:
            fields[str(name)] = payload.decode(part.get_content_charset() or "utf-8", "replace")
    return fields, files


def _path_with_query(path: str, auth_suffix: str = "", **extra: str) -> str:
    params = urllib.parse.parse_qs(auth_suffix.removeprefix("?"), keep_blank_values=True)
    for key, value in extra.items():
        params[key] = [value]
    encoded = urllib.parse.urlencode({key: values[-1] for key, values in params.items()})
    return f"{path}?{encoded}" if encoded else path


class LocalCompanionServer:
    """Serveur HTTP local. L'accès LAN doit être explicitement activé."""

    def __init__(
        self,
        database: Database,
        profiles_by_id: Mapping[str, Mapping[str, Any]],
        *,
        token: str | None = None,
    ):
        self.database = database
        self.profiles_by_id = profiles_by_id
        self.advanced = AdvancedRepository(database)
        self.features = FeatureRepository(database)
        self.photos = PhotoService(database)
        self.pairing = DevicePairingService(database)
        self.token = token or secrets.token_urlsafe(24)
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.host = "127.0.0.1"
        self.port = 0

    @property
    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive() and self.server)

    @property
    def base_url(self) -> str:
        host = _local_ip() if self.host == "0.0.0.0" else self.host
        return f"http://{host}:{self.port}"

    @property
    def access_url(self) -> str:
        return f"{self.base_url}/?token={urllib.parse.quote(self.token)}"

    def create_pairing_session(self, *, ttl_seconds: int = 300) -> PairingSession:
        if not self.running:
            raise RuntimeError("Démarrez d'abord le compagnon local.")
        if self.host != "0.0.0.0":
            raise RuntimeError("Activez le compagnon sur le réseau local avant d'associer un téléphone.")
        return self.pairing.create_session(self.base_url, ttl_seconds=ttl_seconds)

    def paired_devices(self) -> list[dict[str, Any]]:
        return self.pairing.list_devices()

    def revoke_device(self, device_id: str) -> bool:
        return self.pairing.revoke(device_id)

    def start(self, *, lan: bool = False, port: int = 8765) -> str:
        if self.running:
            return self.access_url
        self.host = "0.0.0.0" if lan else "127.0.0.1"
        service = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "AssistantBotaniqueLocal/2.0"

            def log_message(self, _format: str, *_args) -> None:
                return

            def _params(self) -> dict[str, list[str]]:
                return urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)

            def _query_token(self) -> str:
                header = self.headers.get("Authorization", "")
                if header.startswith("Bearer "):
                    return header[7:]
                return (self._params().get("token") or [""])[0]

            def _device_token(self) -> str:
                cookie = SimpleCookie()
                try:
                    cookie.load(self.headers.get("Cookie", ""))
                except Exception:
                    return ""
                morsel = cookie.get(DEVICE_COOKIE)
                return urllib.parse.unquote(morsel.value) if morsel else ""

            def _authorization_mode(self) -> str | None:
                cached = getattr(self, "_cached_auth_mode", None)
                if cached is not None:
                    return cached or None
                query_token = self._query_token()
                if query_token and secrets.compare_digest(query_token, service.token):
                    self._cached_auth_mode = "global"
                    return "global"
                device = service.pairing.authenticate(self._device_token())
                if device:
                    self._paired_device = device
                    self._cached_auth_mode = "device"
                    return "device"
                self._cached_auth_mode = ""
                return None

            def _authorized(self) -> bool:
                return self._authorization_mode() is not None

            def _auth_suffix(self) -> str:
                if self._authorization_mode() == "global":
                    return f"?token={urllib.parse.quote(service.token)}"
                return ""

            def _send(
                self,
                content: str | bytes,
                *,
                status: int = HTTPStatus.OK,
                content_type: str = "text/html; charset=utf-8",
                cache_control: str = "no-store",
            ) -> None:
                raw = content.encode("utf-8") if isinstance(content, str) else content
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", cache_control)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
                    "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
                )
                self.end_headers()
                self.wfile.write(raw)

            def _json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
                self._send(json.dumps(payload, ensure_ascii=False), status=status, content_type="application/json; charset=utf-8")

            def _redirect(self, path: str, *, cookie: str | None = None) -> None:
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", path)
                if cookie:
                    self.send_header("Set-Cookie", cookie)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()

            def _forbidden(self) -> None:
                self._send(
                    service._message_page("Accès refusé", "Ce téléphone n'est pas associé ou son accès a été révoqué."),
                    status=HTTPStatus.FORBIDDEN,
                )

            def _pair_code(self, path: str) -> str:
                return urllib.parse.unquote(path.removeprefix("/pair/")).strip()

            def do_GET(self) -> None:
                path = urllib.parse.urlsplit(self.path).path
                if path == "/manifest.webmanifest":
                    self._send(service._manifest(), content_type="application/manifest+json; charset=utf-8", cache_control="public, max-age=3600")
                    return
                if path == "/service-worker.js":
                    self._send(service._service_worker(), content_type="application/javascript; charset=utf-8", cache_control="no-cache")
                    return
                if path == "/icon.svg":
                    self._send(service._icon_svg(), content_type="image/svg+xml; charset=utf-8", cache_control="public, max-age=86400")
                    return
                if path == "/offline":
                    self._send(service._offline_page(), cache_control="public, max-age=3600")
                    return
                if path.startswith("/pair/"):
                    code = self._pair_code(path)
                    self._send(service._pairing_page(code, valid=service.pairing.session_is_valid(code)))
                    return
                if not self._authorized():
                    self._forbidden()
                    return
                suffix = self._auth_suffix()
                if path == "/api/plants":
                    self._json(service.database.load_plants())
                    return
                if path == "/api/sensors":
                    self._json(service.advanced.latest_sensor_readings())
                    return
                if path == "/api/inventory":
                    self._json(service.features.list_inventory_enriched())
                    return
                if path == "/api/photos":
                    plant_id = (self._params().get("plant_id") or [""])[0]
                    self._json(service.database.list_photos(plant_id or None))
                    return
                if path == "/api/sync":
                    tasks = CarePlanner(service.database).due_tasks(date.today())
                    self._json(
                        {
                            "synced_at": datetime.now().isoformat(timespec="seconds"),
                            "plants": len(service.database.load_plants()),
                            "due_tasks": len(tasks),
                            "photos": len(service.database.list_photos()),
                            "inventory": len(service.features.list_inventory_enriched()),
                        }
                    )
                    return
                if path == "/stock":
                    saved = (self._params().get("saved") or [""])[0] == "1"
                    self._send(service._stock_page(suffix, saved=saved))
                    return
                if path.startswith("/plant/"):
                    plant_id = urllib.parse.unquote(path.removeprefix("/plant/"))
                    self._send(
                        service._plant_page(
                            plant_id,
                            suffix,
                            photo_added=(self._params().get("photo") or [""])[0] == "added",
                        )
                    )
                    return
                if path == "/":
                    device = getattr(self, "_paired_device", None)
                    self._send(service._home_page(suffix, device_name=str(device.get("name")) if device else ""))
                    return
                self._send("<h1>Page introuvable</h1>", status=HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                path = urllib.parse.urlsplit(self.path).path
                if path.startswith("/pair/"):
                    length = min(int(self.headers.get("Content-Length", "0") or 0), 16_384)
                    payload = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
                    try:
                        token = service.pairing.redeem(
                            self._pair_code(path),
                            (payload.get("device_name") or ["Téléphone"])[0],
                        )
                    except ValueError as exc:
                        self._send(service._message_page("Appairage impossible", str(exc)), status=HTTPStatus.GONE)
                        return
                    cookie = (
                        f"{DEVICE_COOKIE}={urllib.parse.quote(token)}; Path=/; HttpOnly; "
                        "SameSite=Strict; Max-Age=31536000"
                    )
                    self._redirect("/", cookie=cookie)
                    return
                if path.startswith("/api/sensor/"):
                    source_id = urllib.parse.unquote(path.removeprefix("/api/sensor/"))
                    length = min(int(self.headers.get("Content-Length", "0") or 0), 1_000_000)
                    try:
                        payload = json.loads(self.rfile.read(length).decode("utf-8"))
                        service.advanced.add_sensor_reading(
                            source_id,
                            float(payload["value"]),
                            recorded_at=payload.get("recorded_at"),
                            unit=payload.get("unit"),
                            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
                            ingest_token=str(payload.get("token") or ""),
                        )
                    except Exception as exc:
                        self._json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                        return
                    self._json({"ok": True}, HTTPStatus.CREATED)
                    return
                if not self._authorized():
                    self._forbidden()
                    return
                suffix = self._auth_suffix()
                if path in {"/api/photo", "/api/diagnostic"}:
                    declared = int(self.headers.get("Content-Length", "0") or 0)
                    limit = (MAX_UPLOAD_BYTES if path == "/api/photo" else MAX_DIAGNOSTIC_BYTES) + 1_000_000
                    if declared <= 0 or declared > limit:
                        self._json(
                            {"ok": False, "error": "Taille de formulaire invalide."},
                            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                        )
                        return
                    fields: dict[str, str] = {}
                    try:
                        fields, files = _multipart_fields(
                            self.headers.get("Content-Type", ""),
                            self.rfile.read(declared),
                        )
                        filename, photo = files["photo"]
                        plant_id = str(fields.get("plant_id") or "")
                        if path == "/api/photo":
                            service.photos.add_photo_bytes(
                                plant_id,
                                photo,
                                filename=filename,
                                caption=str(fields.get("caption") or ""),
                            )
                        else:
                            report = analyze_photo(photo)
                            service.features.save_photo_diagnostic(
                                plant_id=plant_id or None,
                                image_name=filename,
                                summary=report.summary,
                                report=report.as_dict(),
                            )
                    except Exception as exc:
                        self._send(
                            service._message_page(
                                "Image refusée",
                                str(exc),
                                plant_id=fields.get("plant_id", ""),
                                auth_suffix=suffix,
                            ),
                            status=HTTPStatus.BAD_REQUEST,
                        )
                        return
                    if path == "/api/diagnostic":
                        self._send(service._diagnostic_page(report, plant_id, suffix))
                    else:
                        self._redirect(
                            _path_with_query(
                                f"/plant/{urllib.parse.quote(plant_id)}",
                                suffix,
                                photo="added",
                            )
                        )
                    return

                length = min(int(self.headers.get("Content-Length", "0") or 0), 1_000_000)
                content_type = self.headers.get("Content-Type", "")
                raw = self.rfile.read(length)
                if "application/json" in content_type:
                    payload = json.loads(raw.decode("utf-8") or "{}")
                else:
                    parsed_form = urllib.parse.parse_qs(raw.decode("utf-8"))
                    payload = {key: values[0] if values else "" for key, values in parsed_form.items()}
                if path == "/api/care":
                    plant_id = str(payload.get("plant_id") or "")
                    action = str(payload.get("action") or "")
                    note = str(payload.get("note") or "")
                    if action not in ALLOWED_QUICK_ACTIONS:
                        self._json({"ok": False, "error": "Action non autorisée."}, HTTPStatus.BAD_REQUEST)
                        return
                    try:
                        service.database.add_care_event(plant_id, action, note=note or action)
                    except Exception as exc:
                        self._json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                        return
                    if "application/json" in content_type:
                        self._json({"ok": True}, HTTPStatus.CREATED)
                    else:
                        self._redirect(f"/plant/{urllib.parse.quote(plant_id)}{suffix}")
                    return
                if path == "/api/inventory":
                    try:
                        item = service.features.save_mobile_inventory_item(payload)
                    except Exception as exc:
                        if "application/json" in content_type:
                            self._json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                        else:
                            self._send(
                                service._message_page("Produit refusé", str(exc), auth_suffix=suffix),
                                status=HTTPStatus.BAD_REQUEST,
                            )
                        return
                    if "application/json" in content_type:
                        self._json({"ok": True, "item": item}, HTTPStatus.CREATED)
                    else:
                        self._redirect(_path_with_query("/stock", suffix, saved="1"))
                    return
                self._json({"ok": False, "error": "Route inconnue."}, HTTPStatus.NOT_FOUND)

        self.server = ThreadingHTTPServer((self.host, int(port)), Handler)
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="assistant-botanique-local-web",
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

    def _home_page(self, auth_suffix: str, *, device_name: str = "") -> str:
        cards = [
            f'<li><a href="/plant/{html.escape(str(plant["id"]))}{auth_suffix}">'
            f'{html.escape(str(plant["surnom"]))}</a></li>'
            for plant in self.database.load_plants()
        ]
        sensors = self.advanced.latest_sensor_readings()
        sensor_html = "".join(
            f"<li>{html.escape(str(item['name']))}: "
            f"{html.escape(str(item.get('value') if item.get('value') is not None else '—'))} "
            f"{html.escape(str(item.get('unit') or item.get('configured_unit') or ''))}</li>"
            for item in sensors
        )
        tasks = CarePlanner(self.database).due_tasks(date.today())
        task_html = "".join(
            f"<li>{html.escape(str(item['nickname']))} — {html.escape(str(item['care_type']))}</li>"
            for item in tasks[:12]
        )
        paired = (
            f"<p class='success'>Téléphone associé : {html.escape(device_name)}. Synchronisation locale active.</p>"
            if device_name else ""
        )
        return self._page(
            "Assistant Botanique",
            f"""
            <h1>Assistant Botanique</h1>{paired}
            <p>Compagnon local installable. Les données et photos restent sur cet ordinateur.</p>
            <nav><a class="button" href="/stock{auth_suffix}">📦 Scanner ou ajouter un produit</a></nav>
            <p><strong>Dernière synchronisation :</strong> {datetime.now():%d/%m/%Y %H:%M:%S}</p>
            <h2>Contrôles et soins du jour</h2><ul>{task_html or '<li>Aucun soin planifié aujourd’hui</li>'}</ul>
            <h2>Collection</h2><ul>{''.join(cards) or '<li>Aucune plante</li>'}</ul>
            <h2>Capteurs</h2><ul>{sensor_html or '<li>Aucune mesure</li>'}</ul>
            """,
        )

    def _plant_page(self, plant_id: str, auth_suffix: str, *, photo_added: bool = False) -> str:
        plant = next((item for item in self.database.load_plants() if item["id"] == plant_id), None)
        if not plant:
            return self._page("Plante introuvable", "<h1>Plante introuvable</h1>")
        buttons = "".join(
            f'<button name="action" value="{html.escape(action)}">{html.escape(label)}</button>'
            for action, label in (
                ("substrat_sec", "Substrat sec"),
                ("encore_humide", "Encore humide"),
                ("arrosage", "Arrosé"),
                ("fertilisation", "Fertilisé"),
                ("observation", "Observation"),
            )
        )
        photo_count = len(self.database.list_photos(plant_id))
        notice = (
            "<p class='success'>Photo ajoutée et intégrée au journal de l'ordinateur.</p>"
            if photo_added else ""
        )
        safe_id = html.escape(plant_id)
        return self._page(
            str(plant["surnom"]),
            f"""
            <h1>{html.escape(str(plant["surnom"]))}</h1>
            <p>{html.escape(str(plant["species_id"]))}</p>
            <p>Dernier arrosage : {html.escape(str(plant["date_arrosage"]))} · {photo_count} photo(s)</p>{notice}
            <section><h2>Prendre une photo</h2>
            <form method="post" action="/api/photo{auth_suffix}" enctype="multipart/form-data">
              <input type="hidden" name="plant_id" value="{safe_id}">
              <label>Photo <input type="file" name="photo" accept="image/jpeg,image/png,image/webp" capture="environment" required></label>
              <label>Légende <input type="text" name="caption" placeholder="Nouvelle pousse, symptôme…"></label>
              <button type="submit">Envoyer vers l'ordinateur</button>
            </form></section>
            <section><h2>Diagnostic assisté par photo</h2>
            <p>L'analyse est locale et indicative.</p>
            <form method="post" action="/api/diagnostic{auth_suffix}" enctype="multipart/form-data">
              <input type="hidden" name="plant_id" value="{safe_id}">
              <label>Photo du symptôme <input type="file" name="photo" accept="image/jpeg,image/png,image/webp" capture="environment" required></label>
              <button type="submit">Analyser la photo</button>
            </form></section>
            <section><h2>Action rapide</h2>
            <form method="post" action="/api/care{auth_suffix}">
              <input type="hidden" name="plant_id" value="{safe_id}">
              <input type="text" name="note" placeholder="Note facultative"><div class="actions">{buttons}</div>
            </form></section>
            <p><a href="/{auth_suffix}">Retour</a></p>
            """,
        )

    def _stock_page(self, auth_suffix: str, *, saved: bool = False) -> str:
        categories = "".join(
            f'<option value="{html.escape(value)}">{html.escape(value)}</option>'
            for value in INVENTORY_CATEGORIES
        )
        units = "".join(
            f'<option value="{html.escape(value)}">{html.escape(value)}</option>'
            for value in INVENTORY_UNITS
        )
        subcategories_json = html.escape(json.dumps(INVENTORY_SUBCATEGORIES, ensure_ascii=False), quote=True)
        items = self.features.list_inventory_enriched()
        item_rows = "".join(
            f"<li><strong>{html.escape(str(item['name']))}</strong> — "
            f"{html.escape(str(item.get('subcategory') or item['category']))} — "
            f"{item['quantity']:g} {html.escape(str(item['unit']))}</li>"
            for item in items[:80]
        )
        notice = "<p class='success'>Produit enregistré dans le stock de l'ordinateur.</p>" if saved else ""
        return self._page(
            "Stock mobile",
            f"""
            <h1>Ajouter un produit</h1>{notice}
            <p>Scannez le code-barres avec l'appareil photo ou saisissez-le manuellement.</p>
            <section>
              <video id="barcode-video" playsinline hidden></video>
              <button type="button" id="scan-barcode">📷 Scanner le code-barres</button>
              <p id="scan-status" class="muted"></p>
              <form method="post" action="/api/inventory{auth_suffix}" id="inventory-form">
                <label>Code-barres <input id="barcode" name="barcode" inputmode="numeric" autocomplete="off"></label>
                <label>Nom du produit <input name="name" required maxlength="160"></label>
                <label>Marque <input name="brand" maxlength="120"></label>
                <label>Catégorie <select id="category" name="category">{categories}</select></label>
                <label>Sous-catégorie <select id="subcategory" name="subcategory"></select></label>
                <label>Unité <select name="unit">{units}</select></label>
                <label>Quantité <input name="quantity" type="number" min="0" step="0.1" value="1" required></label>
                <label>Seuil d'alerte <input name="threshold" type="number" min="0" step="0.1" value="0"></label>
                <label>Expiration <input name="expires_on" type="date"></label>
                <label>Notes <textarea name="notes" rows="3"></textarea></label>
                <button type="submit">Enregistrer le produit</button>
              </form>
            </section>
            <h2>Stock actuel</h2><ul>{item_rows or '<li>Aucun produit</li>'}</ul>
            <p><a href="/{auth_suffix}">Retour</a></p>
            <script>
            const subcategories = JSON.parse("{subcategories_json}");
            const category = document.getElementById('category');
            const subcategory = document.getElementById('subcategory');
            function refreshSubcategories() {{
              subcategory.innerHTML = '';
              (subcategories[category.value] || subcategories['Autre'] || []).forEach(value => {{
                const option = document.createElement('option');
                option.value = value; option.textContent = value; subcategory.appendChild(option);
              }});
            }}
            category.addEventListener('change', refreshSubcategories); refreshSubcategories();
            const scanButton = document.getElementById('scan-barcode');
            const status = document.getElementById('scan-status');
            const video = document.getElementById('barcode-video');
            scanButton.addEventListener('click', async () => {{
              if (!('BarcodeDetector' in window) || !navigator.mediaDevices?.getUserMedia) {{
                status.textContent = 'Lecture automatique indisponible sur ce navigateur. Saisissez le numéro manuellement.'; return;
              }}
              let stream;
              try {{
                const detector = new BarcodeDetector({{formats:['ean_13','ean_8','upc_a','upc_e','code_128','code_39','itf']}});
                stream = await navigator.mediaDevices.getUserMedia({{video:{{facingMode:'environment'}}}});
                video.srcObject = stream; video.hidden = false; await video.play();
                status.textContent = 'Cadrez le code-barres…';
                const deadline = Date.now() + 20000;
                while (Date.now() < deadline) {{
                  const results = await detector.detect(video);
                  if (results.length) {{
                    document.getElementById('barcode').value = results[0].rawValue;
                    status.textContent = 'Code détecté.'; break;
                  }}
                  await new Promise(resolve => setTimeout(resolve, 350));
                }}
              }} catch (error) {{ status.textContent = 'Scanner indisponible : ' + error.message; }}
              finally {{ if (stream) stream.getTracks().forEach(track => track.stop()); video.hidden = true; }}
            }});
            </script>
            """,
        )

    def _diagnostic_page(self, report, plant_id: str, auth_suffix: str) -> str:
        findings = "".join(
            "<section><h2>" + html.escape(item.title) + "</h2>"
            + f"<p><strong>Confiance :</strong> {html.escape(item.confidence)}</p>"
            + f"<p>{html.escape(item.explanation)}</p><ul>"
            + "".join(f"<li>{html.escape(check)}</li>" for check in item.checks)
            + "</ul></section>"
            for item in report.findings
        )
        back = f"/plant/{urllib.parse.quote(plant_id)}{auth_suffix}" if plant_id else f"/{auth_suffix}"
        return self._page(
            "Diagnostic photo",
            f"<h1>{html.escape(report.summary)}</h1>{findings}"
            f"<p class='warning'>{html.escape(report.disclaimer)}</p><p><a href='{back}'>Retour</a></p>",
        )

    def _pairing_page(self, code: str, *, valid: bool) -> str:
        if not valid:
            return self._page(
                "QR code expiré",
                "<h1>QR code expiré</h1><p>Générez un nouveau code depuis l’ordinateur.</p>",
            )
        safe_code = urllib.parse.quote(code)
        return self._page(
            "Associer ce téléphone",
            f"""
            <h1>Associer ce téléphone</h1>
            <p>Cette association donne accès à la collection, aux soins, au stock et aux photos sur ce réseau local.</p>
            <form method="post" action="/pair/{safe_code}">
              <label>Nom de l’appareil <input name="device_name" maxlength="80" value="Mon téléphone" required></label>
              <button type="submit">Associer et synchroniser</button>
            </form><p>Le QR code est à usage unique et expire après cinq minutes.</p>
            """,
        )

    def _message_page(
        self,
        title: str,
        message: str,
        *,
        plant_id: str = "",
        auth_suffix: str = "",
    ) -> str:
        back = f"/plant/{urllib.parse.quote(plant_id)}{auth_suffix}" if plant_id else f"/{auth_suffix}"
        return self._page(
            title,
            f"<h1>{html.escape(title)}</h1><p>{html.escape(message)}</p><p><a href='{back}'>Retour</a></p>",
        )

    @staticmethod
    def _manifest() -> str:
        return json.dumps(
            {
                "name": "Assistant Botanique",
                "short_name": "Botanique",
                "start_url": "/",
                "scope": "/",
                "display": "standalone",
                "background_color": "#f4f8f1",
                "theme_color": "#2f6f3e",
                "description": "Compagnon local de gestion des plantes et du stock.",
                "icons": [
                    {
                        "src": "/icon.svg",
                        "sizes": "any",
                        "type": "image/svg+xml",
                        "purpose": "any maskable",
                    }
                ],
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _service_worker() -> str:
        return """
const CACHE='assistant-botanique-shell-v2';
const SHELL=['/offline','/manifest.webmanifest','/icon.svg'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL))));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))))));
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET') return;
  const url=new URL(event.request.url);
  if(url.pathname==='/manifest.webmanifest'||url.pathname==='/icon.svg'||url.pathname==='/offline'){
    event.respondWith(caches.match(event.request).then(hit=>hit||fetch(event.request))); return;
  }
  if(event.request.mode==='navigate') event.respondWith(fetch(event.request).catch(()=>caches.match('/offline')));
});
"""

    @staticmethod
    def _icon_svg() -> str:
        return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="96" fill="#2f6f3e"/><path d="M256 420V224" stroke="#fff" stroke-width="34" stroke-linecap="round"/><path d="M254 264C116 250 82 142 92 78c91 4 177 49 185 166" fill="#9bd18b" stroke="#fff" stroke-width="18"/><path d="M258 314c125-11 177-91 170-164-86 2-159 44-174 142" fill="#c6e8ad" stroke="#fff" stroke-width="18"/></svg>"""

    @classmethod
    def _offline_page(cls) -> str:
        return cls._page(
            "Hors connexion",
            "<h1>Hors connexion</h1><p>Reconnectez le téléphone au réseau local de l'ordinateur pour accéder aux données.</p>",
        )

    @staticmethod
    def _page(title: str, body: str) -> str:
        return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{html.escape(title)}</title><meta name="theme-color" content="#2f6f3e"><link rel="manifest" href="/manifest.webmanifest"><link rel="icon" href="/icon.svg">
<style>
:root {{ color-scheme:light dark; }} body {{ font-family:system-ui,sans-serif; max-width:760px; margin:auto; padding:20px; line-height:1.45; }}
li {{ margin:10px 0; }} section {{ border:1px solid #8888; border-radius:12px; padding:14px; margin:18px 0; }}
button,.button {{ display:inline-block; padding:12px; margin:8px 4px; min-height:44px; border-radius:8px; }}
input,select,textarea {{ display:block; box-sizing:border-box; padding:10px; margin:8px 0 14px; width:min(100%,520px); }}
video {{ width:100%; max-height:320px; background:#111; border-radius:10px; }}
.actions {{ margin-top:10px; }} .success {{ padding:10px; background:#d9f8df; color:#123d1d; border-radius:8px; }}
.warning {{ padding:10px; background:#fff0c7; color:#4a3500; border-radius:8px; }} .muted {{ opacity:.75; }}
</style></head><body>{body}<script>if('serviceWorker' in navigator) navigator.serviceWorker.register('/service-worker.js').catch(()=>{{}});</script></body></html>"""
