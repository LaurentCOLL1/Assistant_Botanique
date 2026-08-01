"""Compagnon web local avec appairage QR, photos et écriture limitée."""
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

from assistant_botanique.infrastructure.advanced_repository import AdvancedRepository
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.device_pairing import DevicePairingService, PairingSession
from assistant_botanique.services.photos import MAX_UPLOAD_BYTES, PhotoService
from assistant_botanique.services.planner import CarePlanner

ALLOWED_QUICK_ACTIONS = {
    "substrat_sec",
    "encore_humide",
    "arrosage",
    "fertilisation",
    "rempotage",
    "taille",
    "traitement",
    "observation",
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
            server_version = "AssistantBotaniqueLocal/1.2"

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
                except Exception:  # noqa: BLE001
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
            ) -> None:
                raw = content.encode("utf-8") if isinstance(content, str) else content
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(raw)

            def _json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
                self._send(
                    json.dumps(payload, ensure_ascii=False),
                    status=status,
                    content_type="application/json; charset=utf-8",
                )

            def _redirect(self, path: str, *, cookie: str | None = None) -> None:
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", path)
                if cookie:
                    self.send_header("Set-Cookie", cookie)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()

            def _forbidden(self) -> None:
                self._send(
                    service._message_page(
                        "Accès refusé",
                        "Ce téléphone n'est pas associé ou son accès a été révoqué.",
                    ),
                    status=HTTPStatus.FORBIDDEN,
                )

            def _pair_code(self, path: str) -> str:
                return urllib.parse.unquote(path.removeprefix("/pair/")).strip()

            def do_GET(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlsplit(self.path)
                path = parsed.path
                if path.startswith("/pair/"):
                    code = self._pair_code(path)
                    valid = service.pairing.session_is_valid(code)
                    self._send(service._pairing_page(code, valid=valid))
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
                        }
                    )
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

            def do_POST(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlsplit(self.path)
                path = parsed.path
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
                    except Exception as exc:  # noqa: BLE001
                        self._json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                        return
                    self._json({"ok": True}, HTTPStatus.CREATED)
                    return
                if not self._authorized():
                    self._forbidden()
                    return
                suffix = self._auth_suffix()
                if path == "/api/photo":
                    declared = int(self.headers.get("Content-Length", "0") or 0)
                    if declared <= 0 or declared > MAX_UPLOAD_BYTES + 1_000_000:
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
                        service.photos.add_photo_bytes(
                            plant_id,
                            photo,
                            filename=filename,
                            caption=str(fields.get("caption") or ""),
                        )
                    except Exception as exc:  # noqa: BLE001
                        self._send(
                            service._message_page(
                                "Photo refusée",
                                str(exc),
                                plant_id=fields.get("plant_id", ""),
                                auth_suffix=suffix,
                            ),
                            status=HTTPStatus.BAD_REQUEST,
                        )
                        return
                    target = _path_with_query(
                        f"/plant/{urllib.parse.quote(plant_id)}",
                        suffix,
                        photo="added",
                    )
                    self._redirect(target)
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
                    except Exception as exc:  # noqa: BLE001
                        self._json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                        return
                    target = f"/plant/{urllib.parse.quote(plant_id)}{suffix}"
                    if "application/json" in content_type:
                        self._json({"ok": True}, HTTPStatus.CREATED)
                    else:
                        self._redirect(target)
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
        cards = []
        for plant in self.database.load_plants():
            plant_id = html.escape(str(plant["id"]))
            cards.append(
                f'<li><a href="/plant/{plant_id}{auth_suffix}">{html.escape(str(plant["surnom"]))}</a></li>'
            )
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
            f"<p class='success'>Téléphone associé : {html.escape(device_name)}. "
            "Les changements sont synchronisés en direct avec l'ordinateur.</p>"
            if device_name else ""
        )
        return self._page(
            "Assistant Botanique",
            f"""
            <h1>Assistant Botanique</h1>
            {paired}
            <p>Compagnon local. Les données et photos restent sur cet ordinateur.</p>
            <p>Ouvrez une plante pour ajouter un soin ou prendre une photo.</p>
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
        return self._page(
            str(plant["surnom"]),
            f"""
            <h1>{html.escape(str(plant["surnom"]))}</h1>
            <p>{html.escape(str(plant["species_id"]))}</p>
            <p>Dernier arrosage : {html.escape(str(plant["date_arrosage"]))} · {photo_count} photo(s)</p>
            {notice}
            <section><h2>Prendre une photo</h2>
            <form method="post" action="/api/photo{auth_suffix}" enctype="multipart/form-data">
              <input type="hidden" name="plant_id" value="{html.escape(plant_id)}">
              <label>Photo <input type="file" name="photo" accept="image/jpeg,image/png,image/webp" capture="environment" required></label>
              <label>Légende <input type="text" name="caption" placeholder="Nouvelle pousse, symptôme…"></label>
              <button type="submit">Envoyer vers l'ordinateur</button>
            </form></section>
            <section><h2>Action rapide</h2>
            <form method="post" action="/api/care{auth_suffix}">
              <input type="hidden" name="plant_id" value="{html.escape(plant_id)}">
              <input type="text" name="note" placeholder="Note facultative">
              <div class="actions">{buttons}</div>
            </form></section>
            <p><a href="/{auth_suffix}">Retour</a></p>
            """,
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
            <p>Cette association donne accès à la collection, aux soins et à l’envoi de photos sur ce réseau local.</p>
            <form method="post" action="/pair/{safe_code}">
              <label>Nom de l’appareil
                <input name="device_name" maxlength="80" value="Mon téléphone" required>
              </label>
              <button type="submit">Associer et synchroniser</button>
            </form>
            <p>Le QR code est à usage unique et expire après cinq minutes.</p>
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
    def _page(title: str, body: str) -> str:
        return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body {{ font-family:system-ui,sans-serif; max-width:760px; margin:auto; padding:20px; line-height:1.45; }}
li {{ margin:10px 0; }} section {{ border:1px solid #aaa; border-radius:10px; padding:14px; margin:18px 0; }}
button {{ padding:12px; margin:8px 4px; min-height:44px; }}
input {{ display:block; box-sizing:border-box; padding:10px; margin:8px 0 14px; width:min(100%,520px); }}
.actions {{ margin-top:10px; }} .success {{ padding:10px; background:#d9f8df; color:#123d1d; border-radius:8px; }}
</style></head><body>{body}</body></html>"""
