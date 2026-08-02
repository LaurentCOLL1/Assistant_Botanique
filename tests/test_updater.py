import io
import json
import urllib.error

from packaging.version import Version

from assistant_botanique.services import updater


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def response(payload):
    return FakeResponse(json.dumps(payload).encode("utf-8"))


def test_no_release_is_not_an_error(monkeypatch):
    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: response([]),
    )
    info = updater.check_for_update()

    assert info.published is False
    assert info.available is False
    assert info.latest == info.current


def test_404_is_still_reported_as_no_release(monkeypatch):
    def raise_404(*_args, **_kwargs):
        raise urllib.error.HTTPError(updater.API_URL, 404, "Not Found", {}, None)

    monkeypatch.setattr(updater.urllib.request, "urlopen", raise_404)
    info = updater.check_for_update()

    assert info.published is False
    assert info.available is False


def test_newer_release_is_detected(monkeypatch):
    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: response(
            [
                {
                    "tag_name": "v99.0.0",
                    "html_url": "https://example.invalid/release",
                    "body": "Notes",
                    "draft": False,
                    "prerelease": False,
                }
            ]
        ),
    )

    info = updater.check_for_update()

    assert info.published is True
    assert info.available is True
    assert info.latest == "99.0.0"
    assert info.prerelease is False


def test_newer_beta_release_is_detected(monkeypatch):
    monkeypatch.setattr(updater, "__version__", "3.5.1b2")
    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: response(
            [
                {
                    "tag_name": "v3.5.1-beta.3",
                    "html_url": "https://example.invalid/beta3",
                    "body": "Beta 3",
                    "draft": False,
                    "prerelease": True,
                },
                {
                    "tag_name": "v3.5.1-beta.2",
                    "html_url": "https://example.invalid/beta2",
                    "body": "Beta 2",
                    "draft": False,
                    "prerelease": True,
                },
            ]
        ),
    )

    info = updater.check_for_update()

    assert info.available is True
    assert info.latest == "3.5.1-beta.3"
    assert info.prerelease is True


def test_stable_release_wins_over_prerelease_of_same_version(monkeypatch):
    monkeypatch.setattr(updater, "__version__", "3.5.1b3")
    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: response(
            [
                {"tag_name": "v3.5.1-beta.4", "draft": False, "prerelease": True},
                {"tag_name": "v3.5.1", "draft": False, "prerelease": False},
            ]
        ),
    )

    info = updater.check_for_update()

    assert info.latest == "3.5.1"
    assert info.available is True
    assert info.prerelease is False


def test_version_normalization_respects_prerelease_order():
    assert updater._version("v3.5.1-alpha.2") < updater._version("3.5.1-beta.1")
    assert updater._version("3.5.1-beta.4") < updater._version("3.5.1-rc.1")
    assert updater._version("3.5.1-rc.1") < Version("3.5.1")
