import json
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

import pytest

from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.local_web import LocalCompanionServer


def sample_plant():
    return {
        "id": "p1",
        "species_id": "epipremnum-aureum",
        "surnom": "Pothos",
        "pot_l": 2,
        "date_arrosage": "01/07/2026",
        "contexte": {"emplacement": "salon"},
        "historique_soins": [],
    }


def test_pairing_qr_creates_persistent_cookie_and_can_be_revoked(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.save_plants([sample_plant()])
    server = LocalCompanionServer(database, {}, token="desktop-token")
    opener = build_opener(HTTPCookieProcessor(CookieJar()))

    try:
        server.start(lan=False, port=0)
        session = server.pairing.create_session(server.base_url, ttl_seconds=300)

        with opener.open(session.url, timeout=5) as response:
            pairing_page = response.read().decode("utf-8")
        assert "Associer ce téléphone" in pairing_page

        request = Request(
            session.url,
            data=urlencode({"device_name": "Téléphone de test"}).encode("utf-8"),
            method="POST",
        )
        with opener.open(request, timeout=5) as response:
            home_page = response.read().decode("utf-8")
        assert "Téléphone associé : Téléphone de test" in home_page
        assert "synchronisés en direct" in home_page

        with opener.open(f"{server.base_url}/api/sync", timeout=5) as response:
            status = json.loads(response.read().decode("utf-8"))
        assert status["plants"] == 1
        assert "synced_at" in status

        devices = server.paired_devices()
        assert len(devices) == 1
        assert devices[0]["name"] == "Téléphone de test"
        assert server.revoke_device(devices[0]["id"])

        with pytest.raises(HTTPError) as error:
            opener.open(f"{server.base_url}/", timeout=5)
        assert error.value.code == 403
    finally:
        server.stop()


def test_pairing_code_is_single_use(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    service = LocalCompanionServer(database, {}).pairing
    session = service.create_session("http://127.0.0.1:8765")

    token = service.redeem(session.code, "Premier téléphone")
    assert service.authenticate(token)
    with pytest.raises(ValueError, match="expiré|utilisé"):
        service.redeem(session.code, "Second téléphone")
