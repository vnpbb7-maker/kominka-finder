"""
scorer.py — Gemini AI scoring pipeline for kominka listings
Scores each listing on kominka authenticity and preservation condition.
"""

import json
import os
import re
from typing import Optional

import google.generativeai as genai
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# gemini-1.5-flash: fast, generous free tier (15 RPM / 1M TPM)
MODEL = "gemini-1.5-flash"

# Keywords that strongly indicate traditional kominka architecture
KOMINKA_KEYWORDS = [
    "古民家", "茅葺", "土間", "囲炉裏", "梁", "古材", "大正", "明治",
    "昭和初期", "古家", "蔵", "納屋", "縁側", "欄間", "格子", "石蔵",
    "庄屋", "武家屋敷", "町家", "長屋門", "水車", "五右衛門風呂"
]

SCORING_PROMPT = """以下の不動産物件情報を分析し、必ずJSON形式のみで返答してください（他のテキスト不要）。

評価項目:
- kominka_score: 古民家らしさ 0-100（100=極めて伝統的な古民家）
- preservation_score: 保存状態・構造的コンディション 0-100（100=非常に良好）
- reason: 判断理由（50文字以内の日本語）

物件情報:
タイトル: {title}
所在地: {location}
築年数情報: {year_built}
建物面積: {area}㎡
説明文: {description}

必ず以下のフォーマットで返してください:
{{"kominka_score": 数値, "preservation_score": 数値, "reason": "理由テキスト"}}"""


def _build_prompt(listing: dict) -> str:
    """Construct the scoring prompt from a listing dict."""
    location = " ".join(filter(None, [
        listing.get("location_prefecture"),
        listing.get("location_city"),
    ])) or "不明"

    year_built = listing.get("year_built")
    year_str = f"{year_built}年建築" if year_built else "不明"

    area = listing.get("area_sqm", "不明")

    description = (listing.get("description") or "")[:500]  # truncate to save tokens

    return SCORING_PROMPT.format(
        title=listing.get("title", ""),
        location=location,
        year_built=year_str,
        area=area,
        description=description,
    )


def _pre_score(listing: dict) -> Optional[int]:
    """
    Fast keyword-based pre-score to boost listings with kominka keywords.
    Returns a bonus 0-20 to add to the AI score, or None if no keywords found.
    """
    text = " ".join(filter(None, [
        listing.get("title", ""),
        listing.get("description", ""),
    ]))
    hits = sum(1 for kw in KOMINKA_KEYWORDS if kw in text)
    if hits == 0:
        return None
    return min(hits * 4, 20)  # up to +20 bonus points


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
def score_listing(model: genai.GenerativeModel, listing: dict) -> dict:
    """
    Call Gemini 1.5 Flash to score a single listing.
    Returns {"kominka_score": int, "preservation_score": int, "reason": str}
    """
    prompt = _build_prompt(listing)

    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=200,
            temperature=0.1,  # low temp for consistent JSON output
        ),
    )

    raw = response.text.strip()

    # Parse and validate the JSON response
    try:
        # Handle cases where model wraps JSON in ```json ... ```
        json_match = re.search(r"\{.*?\}", raw, re.DOTALL)
        if not json_match:
            raise ValueError(f"No JSON in response: {raw}")

        scores = json.loads(json_match.group())

        # Clamp values to valid range
        scores["kominka_score"] = max(0, min(100, int(scores.get("kominka_score", 0))))
        scores["preservation_score"] = max(0, min(100, int(scores.get("preservation_score", 0))))
        scores["score_reason"] = str(scores.get("reason", ""))[:200]

        # Apply keyword bonus
        bonus = _pre_score(listing)
        if bonus:
            scores["kominka_score"] = min(100, scores["kominka_score"] + bonus)

        return scores

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.error(f"Score parse error: {e} | Raw: {raw}")
        raise  # tenacity will retry


def score_batch(listings: list[dict], db_client=None) -> list[dict]:
    """
    Score a batch of listings and optionally write scores back to Supabase.
    Returns list of listings with scores attached.
    """
    # Initialize Gemini client once per batch
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL)
    scored = []

    for i, listing in enumerate(listings):
        listing_id = listing.get("id", "?")
        try:
            logger.info(f"Scoring [{i+1}/{len(listings)}] id={listing_id}")
            scores = score_listing(model, listing)
            listing.update(scores)
            scored.append(listing)

            if db_client and listing.get("id"):
                from db import update_scores
                update_scores(db_client, listing["id"], {
                    "kominka_score": scores["kominka_score"],
                    "preservation_score": scores["preservation_score"],
                    "score_reason": scores["score_reason"],
                })

        except Exception as e:
            logger.error(f"Failed to score listing {listing_id}: {e}")
            listing["kominka_score"] = 0
            listing["preservation_score"] = 0
            listing["score_reason"] = "スコアリング失敗"
            scored.append(listing)

    logger.info(f"Scoring complete: {len(scored)} listings processed")
    return scored
