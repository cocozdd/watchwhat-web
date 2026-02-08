from app.services.cookie_capture import CookieCaptureManager


def test_cookie_persistence_survives_manager_reinit(tmp_path):
    store_path = tmp_path / "cookies.json"

    manager1 = CookieCaptureManager(
        persist_path=str(store_path),
        enable_persistence=True,
    )
    manager1.set_cookie("douban", "dbcl2=abc123; ck=xyz")

    manager2 = CookieCaptureManager(
        persist_path=str(store_path),
        enable_persistence=True,
    )
    assert manager2.get_cookie("douban") is not None
    assert "dbcl2=abc123" in manager2.get_cookie("douban")


def test_cookie_persistence_clear_updates_store(tmp_path):
    store_path = tmp_path / "cookies.json"

    manager = CookieCaptureManager(
        persist_path=str(store_path),
        enable_persistence=True,
    )
    manager.set_cookie("douban", "dbcl2=abc123; ck=xyz")
    manager.clear_cookie("douban")

    reloaded = CookieCaptureManager(
        persist_path=str(store_path),
        enable_persistence=True,
    )
    assert reloaded.get_cookie("douban") is None
