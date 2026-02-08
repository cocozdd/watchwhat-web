import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Tuple

try:
    from opencc import OpenCC  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    OpenCC = None


@dataclass
class SeriesIdentity:
    series_key: str
    series_display_title_zh: str
    raw_title: str
    is_variant: bool


_T2S_MAP: Dict[str, str] = {
    "島": "岛",
    "來": "来",
    "訪": "访",
    "與": "与",
    "雲": "云",
    "風": "风",
    "說": "说",
    "讀": "读",
    "寫": "写",
    "書": "书",
    "門": "门",
    "開": "开",
    "關": "关",
    "國": "国",
    "體": "体",
    "學": "学",
    "術": "术",
    "業": "业",
    "畫": "画",
    "劍": "剑",
    "龍": "龙",
    "貓": "猫",
    "馬": "马",
    "劇": "剧",
    "樂": "乐",
    "愛": "爱",
    "憶": "忆",
    "歷": "历",
    "時": "时",
    "點": "点",
    "頭": "头",
    "發": "发",
    "變": "变",
    "記": "记",
    "偵": "侦",
    "謎": "谜",
    "獄": "狱",
    "處": "处",
    "後": "后",
    "臺": "台",
    "萬": "万",
    "為": "为",
    "無": "无",
    "麵": "面",
    "們": "们",
    "這": "这",
    "個": "个",
    "裡": "里",
    "裏": "里",
    "過": "过",
}

_OPENCC_T2S = OpenCC("t2s") if OpenCC is not None else None


def _normalize_script(value: str) -> str:
    text = value or ""
    if _OPENCC_T2S is not None:
        try:
            return _OPENCC_T2S.convert(text)
        except Exception:
            pass
    return "".join(_T2S_MAP.get(ch, ch) for ch in text)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _compact_key(value: str) -> str:
    normalized = _normalize_script(_normalize_text(value)).lower()
    normalized = re.sub(r"[`'\"“”‘’·・･,，.。:：;；!?！？()\[\]{}<>《》【】/\\|+*&^%$#@~\-]+", " ", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


_ALIASES: Dict[str, Tuple[str, str]] = {
    _compact_key("one piece"): ("series:one_piece", "海贼王"),
    _compact_key("onepiece"): ("series:one_piece", "海贼王"),
    _compact_key("ワンピース"): ("series:one_piece", "海贼王"),
    _compact_key("海贼王"): ("series:one_piece", "海贼王"),
    _compact_key("航海王"): ("series:one_piece", "海贼王"),
    _compact_key("名探偵に甘美なる死を"): ("series:amai_shi_for_detective", "献给名侦探的甜美死亡"),
    _compact_key("献给名侦探的甜美死亡"): ("series:amai_shi_for_detective", "献给名侦探的甜美死亡"),
    _compact_key("そして誰も死ななかった"): ("series:soshite_daremo_shinanakatta", "无人逝去"),
    _compact_key("无人逝去"): ("series:soshite_daremo_shinanakatta", "无人逝去"),
}


_SUFFIX_PATTERNS = [
    r"[\s:：\-–—]*(?:第?\s*\d+\s*[卷册部季篇话集章巻])$",
    r"[\s:：\-–—]*(?:vol(?:ume)?\.?\s*\d+)$",
    r"[\s:：\-–—]*(?:#\s*\d+)$",
    r"[\s:：\-–—]*(?:season\s*\d+)$",
    r"[\s:：\-–—]*(?:s\d+)$",
    r"[\s:：\-–—]*(?:part\s*\d+)$",
    r"[\s:：\-–—]+\d{1,3}$",
]


def _strip_series_suffix(title: str) -> Tuple[str, bool]:
    current = _normalize_text(title)
    changed = False
    for _ in range(3):
        previous = current
        for pattern in _SUFFIX_PATTERNS:
            current = re.sub(pattern, "", current, flags=re.IGNORECASE)
        current = current.strip(" -_:：·.").strip()
        if current == previous:
            break
        changed = True
    if not current:
        return _normalize_text(title), changed
    return current, changed


def build_series_identity(title: str, item_type: str) -> SeriesIdentity:
    raw_title = _normalize_text(title)
    stripped_title, removed_variant_suffix = _strip_series_suffix(raw_title)
    stripped_key = _compact_key(stripped_title)
    alias = _ALIASES.get(stripped_key)

    if alias is not None:
        series_suffix, canonical_zh = alias
        series_key = f"{item_type}:{series_suffix}"
        raw_key = _compact_key(raw_title)
        canonical_key = _compact_key(canonical_zh)
        is_variant = removed_variant_suffix or (raw_key != canonical_key)
        return SeriesIdentity(
            series_key=series_key,
            series_display_title_zh=canonical_zh,
            raw_title=raw_title,
            is_variant=is_variant,
        )

    base_key = stripped_key or _compact_key(raw_title) or "unknown"
    return SeriesIdentity(
        series_key=f"{item_type}:{base_key}",
        series_display_title_zh=stripped_title or raw_title,
        raw_title=raw_title,
        is_variant=removed_variant_suffix,
    )
