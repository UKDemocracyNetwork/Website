import os

import requests

BASE_URL = os.environ.get("SMOKE_URL", "http://localhost:8080")


def test_homepage_200():
    r = requests.get(BASE_URL + "/", timeout=10)
    assert r.status_code == 200


def test_homepage_has_h1():
    r = requests.get(BASE_URL + "/", timeout=10)
    assert "<h1" in r.text


def test_ghost_admin_reachable():
    r = requests.get(BASE_URL + "/ghost/", allow_redirects=True, timeout=10)
    assert r.status_code == 200


def test_ghost_admin_not_publicly_cached():
    r = requests.get(BASE_URL + "/ghost/", allow_redirects=True, timeout=10)
    cc = r.headers.get("Cache-Control", "")
    assert any(directive in cc for directive in ("no-store", "no-cache", "private")), (
        f"Unexpected Cache-Control on /ghost/: {cc!r}"
    )
