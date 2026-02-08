from app.services.cookie_capture import extract_cookie_text, has_login_cookie


def test_has_login_cookie_requires_dbcl2():
    assert has_login_cookie({"bid", "ck"}) is False
    assert has_login_cookie({"dbcl2"}) is True


def test_extract_cookie_text_deduplicates_and_keeps_latest_value():
    cookies = [
        {"name": "bid", "value": "guest1"},
        {"name": "dbcl2", "value": "acctA"},
        {"name": "ck", "value": "first"},
        {"name": "ck", "value": "second"},
        {"name": "Path", "value": "/"},
    ]

    text = extract_cookie_text(cookies)

    assert "dbcl2=acctA" in text
    assert "ck=second" in text
    assert "ck=first" not in text
    assert "Path=" not in text
