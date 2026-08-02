from io import BytesIO
import urllib.parse
import urllib.request
from uuid import uuid4

import qrcode

from assistant_botanique.features.followup_fixes import (
    install_followup_fixes,
    rewrite_stock_page,
)
from assistant_botanique.features.usability_fixes import install_usability_fixes
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.local_web import LocalCompanionServer


def _stock_page_source() -> str:
    return """<!doctype html><html><body>
<section>
<video id="barcode-video" playsinline hidden></video>
<button type="button" id="scan-barcode">📷 Scanner le code-barres</button>
<p id="scan-status" class="muted"></p>
<form method="post" action="/api/inventory?token=test" id="inventory-form">
<label>Code-barres <input id="barcode" name="barcode" inputmode="numeric" autocomplete="off"></label>
<label>Catégorie <select id="category"><option value="Substrat">Substrat</option></select></label>
<label>Sous-catégorie <select id="subcategory"></select></label>
</form>
</section>
<script>
const subcategories = JSON.parse("{}");
const scanButton = document.getElementById('scan-barcode');
scanButton.addEventListener('click', async () => { await fetch('/old'); });
</script>
</body></html>"""


def _multipart_image(payload: bytes) -> tuple[bytes, str]:
    boundary = f"----assistant-botanique-{uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="photo"; filename="code.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode("ascii") + payload + f"\r\n--{boundary}--\r\n".encode("ascii")
    return body, f"multipart/form-data; boundary={boundary}"


def test_stock_page_has_one_same_origin_scanner_without_fetch():
    page = rewrite_stock_page(
        _stock_page_source(),
        "?token=test",
        barcode="5901234123457",
    )

    assert page.count("📷 Scanner le code-barres") == 1
    assert "Photographier le code-barres" not in page
    assert "Choisir un fichier" not in page
    assert 'action="/api/barcode?token=test"' in page
    assert 'id="same-origin-barcode-photo"' in page
    assert 'value="5901234123457"' in page
    assert "fetch(" not in page
    assert "Failed to fetch" not in page


def test_barcode_photo_uses_the_companion_server_port(tmp_path):
    install_usability_fixes()
    install_followup_fixes()
    database = Database(tmp_path / "same-origin.sqlite3")
    server = LocalCompanionServer(database, {})
    server.start(lan=False, port=0)
    try:
        image = qrcode.make("5901234123457")
        output = BytesIO()
        image.save(output, format="PNG")
        body, content_type = _multipart_image(output.getvalue())
        token = urllib.parse.quote(server.token)
        request = urllib.request.Request(
            f"{server.base_url}/api/barcode?token={token}",
            data=body,
            method="POST",
            headers={"Content-Type": content_type},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            returned_page = response.read().decode("utf-8")
            final_url = response.geturl()

        assert urllib.parse.urlsplit(final_url).port == server.port
        assert urllib.parse.urlsplit(final_url).path == "/stock"
        assert 'value="5901234123457"' in returned_page
        assert returned_page.count("📷 Scanner le code-barres") == 1
        assert "fetch(" not in returned_page
    finally:
        server.stop()
