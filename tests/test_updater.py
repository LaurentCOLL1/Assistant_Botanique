import io
import json
import urllib.error

from assistant_botanique.services import updater


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_no_release_is_not_an_error(monkeypatch):
    def raise_404(*_args, **_kwargs):
        raise urllib.error.HTTPError(updater.API_URL, 404, "Not Found", {}, None)

    monkeypatch.setattr(updater.urllib.request, "urlopen", raise_404)
    info = updater.check_for_update()

    assert info.published is False
    assert info.available is False
    assert info.latest == info.current


def test_newer_release_is_detected(monkeypatch):
    payload = json.dumps(
        {
            "tag_name": "v99.0.0",
            "html_url": "https://example.invalid/release",
            "body": "Notes",
        }
    ).encode("utf-8")
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse(payload))

    info = updater.check_for_update()

    assert info.published is True
    assert info.available is True
    assert info.latest == "99.0.0"
