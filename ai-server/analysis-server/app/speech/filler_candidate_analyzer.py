"""Versioned Korean filler-candidate matching for manual review."""

from __future__ import annotations

import json
from pathlib import Path
import re
import unicodedata
from typing import Any

from .speech_contracts import SpeechAnalysisProfile, SpeechContractError


LEXICON_PATH = Path(__file__).parent / "config" / "filler_candidates.ko.v1.json"


def normalize_candidate(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).casefold()
    return "".join(
        character
        for character in normalized
        if not character.isspace() and not re.match(r"[^\w가-힣]", character)
    )


def load_lexicon(
    profile: SpeechAnalysisProfile, path: str | Path = LEXICON_PATH
) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise SpeechContractError("FILLER_LEXICON_INVALID", "Filler lexicon unavailable") from exc
    if (
        payload.get("name") != profile.filler_lexicon_name
        or payload.get("version") != profile.filler_lexicon_version
        or not isinstance(payload.get("entries"), list)
    ):
        raise SpeechContractError("FILLER_LEXICON_INVALID", "Filler lexicon contract mismatch")
    return payload


def analyze_filler_candidates(
    words: list[dict[str, Any]],
    duration_ms: int,
    profile: SpeechAnalysisProfile,
    *,
    lexicon: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    source = lexicon or load_lexicon(profile)
    entries = {normalize_candidate(str(entry)) for entry in source["entries"]}
    candidates: list[dict[str, Any]] = []
    for word in words:
        raw = str(word.get("text", ""))
        normalized = normalize_candidate(raw)
        if normalized not in entries:
            continue
        candidates.append(
            {
                "candidateText": raw,
                "normalizedText": normalized,
                "wordId": word["wordId"],
                "startMsRelative": int(word["startMsRelative"]),
                "endMsRelative": int(word["endMsRelative"]),
                "startMsSession": int(word["startMsSession"]),
                "endMsSession": int(word["endMsSession"]),
                "matchType": "NORMALIZED_EXACT",
                "candidateType": "FILLER_CANDIDATE",
                "reviewRequired": True,
            }
        )
    total_duration = sum(
        item["endMsRelative"] - item["startMsRelative"] for item in candidates
    )
    summary = {
        "lexiconName": source["name"],
        "lexiconVersion": source["version"],
        "classification": "CANDIDATE_ONLY",
        "fillerCandidateCount": len(candidates),
        "fillerCandidateDurationMs": total_duration,
        "fillerCandidatesPerMinute": (
            round(len(candidates) * 60_000 / duration_ms, 6)
            if duration_ms > 0
            else None
        ),
        "uniqueFillerCandidateCount": len(
            {item["normalizedText"] for item in candidates}
        ),
        "manualReviewRequired": bool(candidates),
    }
    warnings = ["FILLER_CANDIDATE_REVIEW_REQUIRED"] if candidates else []
    return candidates, summary, warnings
