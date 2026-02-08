from app.services.series_normalizer import build_series_identity


def test_one_piece_aliases_are_grouped_to_same_series():
    a = build_series_identity("One Piece Vol.1", "book")
    b = build_series_identity("海贼王 第1卷", "book")
    c = build_series_identity("ワンピース 1", "book")

    assert a.series_key == b.series_key == c.series_key
    assert a.series_display_title_zh == "海贼王"
    assert b.series_display_title_zh == "海贼王"
    assert c.series_display_title_zh == "海贼王"


def test_non_series_title_is_not_mis_grouped():
    identity = build_series_identity("1984", "book")

    assert identity.series_display_title_zh == "1984"
    assert identity.series_key.startswith("book:")
    assert identity.is_variant is False


def test_traditional_and_simplified_titles_are_grouped_to_same_series():
    simplified = build_series_identity("孤岛的来访者", "book")
    traditional = build_series_identity("孤島的來訪者", "book")

    assert simplified.series_key == traditional.series_key


def test_japanese_and_chinese_titles_are_grouped_for_detective_case():
    jp = build_series_identity("名探偵に甘美なる死を", "book")
    zh = build_series_identity("献给名侦探的甜美死亡", "book")

    assert jp.series_key == zh.series_key


def test_japanese_and_chinese_titles_are_grouped_for_and_then_no_one_died():
    jp = build_series_identity("そして誰も死ななかった", "book")
    zh = build_series_identity("无人逝去", "book")

    assert jp.series_key == zh.series_key
    assert zh.series_display_title_zh == "无人逝去"
