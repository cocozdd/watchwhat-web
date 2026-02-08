import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

import httpx

from app.config import get_settings
from app.services.adapters.base import CandidateItem


@dataclass
class RankedChoice:
    subject_id: str
    score: float
    reason: str


@dataclass
class LLMRecommendation:
    low_confidence: bool
    followup_question: Optional[str]
    ranked: List[RankedChoice]


class DeepSeekClient:
    def __init__(self):
        self.settings = get_settings()

    def configured(self) -> bool:
        return bool(self.settings.deepseek_api_key)

    def recommend(
        self,
        query: str,
        profile_summary: str,
        candidates: List[CandidateItem],
        allow_followup: bool,
        strict_types: Optional[Set[str]] = None,
        language_preference: str = "zh_preferred",
    ) -> LLMRecommendation:
        if not self.configured():
            raise RuntimeError("DeepSeek is not configured")

        prompt_candidates: List[Dict[str, str]] = []
        for candidate in candidates[:80]:
            metadata = candidate.metadata or {}
            prompt_candidates.append(
                {
                    "subject_id": candidate.subject_id,
                    "title": candidate.title,
                    "type": candidate.type,
                    "year": str(candidate.year) if candidate.year else "",
                    "series_key": metadata.get("series_key", ""),
                    "display_title_zh": metadata.get("series_title_zh", ""),
                    "is_series_variant": metadata.get("is_series_variant", "false"),
                }
            )

        system_prompt = (
            "你是推荐重排器，只返回严格 JSON，字段必须是："
            "low_confidence(bool), followup_question(string|null), "
            "ranked(list[{subject_id, score(0-1), reason}])。"
            "规则：当 strict_types 非空时必须严格遵守类型，不允许越界；"
            "同一 series_key 最多 1 条；标题优先中文 display_title_zh；理由必须中文且简洁。"
        )
        user_payload = {
            "user_query": query,
            "allow_followup": allow_followup,
            "profile_summary": profile_summary,
            "strict_types": sorted(strict_types) if strict_types else [],
            "language_preference": language_preference,
            "candidates": prompt_candidates,
        }

        payload = {
            "model": self.settings.deepseek_model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
        }

        url = self.settings.deepseek_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.settings.request_timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()

        content = body["choices"][0]["message"]["content"]
        data = _extract_json(content)

        ranked = []
        candidate_map = {candidate.subject_id: candidate for candidate in candidates}
        used_series = set()
        strict_types_set = set(strict_types or set())
        for entry in data.get("ranked", []):
            subject_id = str(entry.get("subject_id", "")).strip()
            if not subject_id:
                continue
            candidate = candidate_map.get(subject_id)
            if candidate is None:
                continue
            if strict_types_set and candidate.type not in strict_types_set:
                continue

            series_key = (candidate.metadata or {}).get("series_key", "")
            if series_key and series_key in used_series:
                continue
            if series_key:
                used_series.add(series_key)

            reason = str(entry.get("reason", "推荐匹配你的偏好")).strip() or "推荐匹配你的偏好"
            try:
                score = float(entry.get("score", 0.5))
            except (TypeError, ValueError):
                score = 0.5
            score = max(0.0, min(1.0, score))
            ranked.append(RankedChoice(subject_id=subject_id, score=score, reason=reason))

        return LLMRecommendation(
            low_confidence=bool(data.get("low_confidence", False)),
            followup_question=data.get("followup_question"),
            ranked=ranked,
        )


def _extract_json(content: str) -> dict:
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("LLM response did not contain JSON")
    return json.loads(raw[start : end + 1])
