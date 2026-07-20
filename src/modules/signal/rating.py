"""Standard 5-level signal rating scale shared by every external signal source.

Mirrors the industry-standard "Strong Buy / Buy / Neutral / Sell / Strong Sell"
scale (e.g. TradingView's ``Recommend.All``, Zacks Rank, sell-side analyst
consensus buckets) so every connector in ``src.modules.com`` normalizes to the
same vocabulary regardless of whether its underlying provider reports a numeric
score, free-text analyst grade, or vote counts. ``src.modules.signal.sources``
then derives the simpler buy/hold/sell ``ExternalSignal.direction`` (used by
existing strategy vote-counting, e.g. ``signal_follow.min_buy_votes``) from
whichever ``rating`` a source produces here.
"""

from __future__ import annotations

RATING_LEVELS: tuple[str, ...] = ("strong_buy", "buy", "neutral", "sell", "strong_sell")


def rating_from_score(
    score: float | None, *, strong_threshold: float = 0.5, buy_threshold: float = 0.1
) -> str | None:
    """Buckets a -1..+1 composite score into the 5-level scale using the same
    thresholds TradingView documents for its own ``Recommend.All`` field:
    >=0.5 Strong Buy, >=0.1 Buy, >-0.1 Neutral, >-0.5 Sell, else Strong Sell."""
    if score is None:
        return None
    if score >= strong_threshold:
        return "strong_buy"
    if score >= buy_threshold:
        return "buy"
    if score > -buy_threshold:
        return "neutral"
    if score > -strong_threshold:
        return "sell"
    return "strong_sell"


# Ordered (substring, rating) rules for free-text analyst grades. Order matters:
# more specific phrases (and words that are substrings of other words, e.g.
# "outperform"/"underperform" both contain "perform") must be checked before
# their broader/generic catch-all entries later in the list.
_TEXT_RULES: tuple[tuple[str, str], ...] = (
    ("strong buy", "strong_buy"),
    ("strong sell", "strong_sell"),
    ("conviction buy", "strong_buy"),
    ("top pick", "strong_buy"),
    ("action list buy", "strong_buy"),
    ("outperform", "buy"),
    ("overweight", "buy"),
    ("accumulate", "buy"),
    ("above average", "buy"),
    ("speculative buy", "buy"),
    ("positive", "buy"),
    ("buy", "buy"),
    ("underperform", "sell"),
    ("underweight", "sell"),
    ("reduce", "sell"),
    ("below average", "sell"),
    ("negative", "sell"),
    ("cautious", "sell"),
    ("sell", "sell"),
    ("equal-weight", "neutral"),
    ("equal weight", "neutral"),
    ("sector weight", "neutral"),
    ("in-line", "neutral"),
    ("in line", "neutral"),
    ("mixed", "neutral"),
    ("hold", "neutral"),
    ("neutral", "neutral"),
    ("perform", "neutral"),
)


def rating_from_text(value: str | None) -> str | None:
    """Best-effort 5-level rating from a provider's free-form rating/grade
    string (e.g. FMP's ``newGrade``/``previousGrade`` values: "Outperform",
    "Sector Underperform", "Equal-Weight", ...). Returns ``None`` if nothing
    recognizable is found."""
    if not value:
        return None
    label = str(value).strip().lower()
    for needle, rating in _TEXT_RULES:
        if needle in label:
            return rating
    return None


# Standard weight per rating level used to collapse analyst vote counts (e.g.
# Finnhub's strongBuy/buy/hold/sell/strongSell buckets, FMP's grades-consensus)
# into a single composite score, then reuse rating_from_score's thresholds.
_VOTE_WEIGHTS: dict[str, float] = {
    "strong_buy": 2.0,
    "buy": 1.0,
    "neutral": 0.0,
    "sell": -1.0,
    "strong_sell": -2.0,
}


def rating_from_vote_counts(
    *, strong_buy: float = 0, buy: float = 0, hold: float = 0, sell: float = 0, strong_sell: float = 0
) -> str | None:
    """Collapses analyst-consensus bucket counts into one rating: a weighted
    average (Strong Buy=+2 ... Strong Sell=-2) normalized to -1..+1 by the
    maximum possible weight, then bucketed via ``rating_from_score``. Returns
    ``None`` if there are no votes at all."""
    total = strong_buy + buy + hold + sell + strong_sell
    if total <= 0:
        return None
    weighted = (
        strong_buy * _VOTE_WEIGHTS["strong_buy"]
        + buy * _VOTE_WEIGHTS["buy"]
        + hold * _VOTE_WEIGHTS["neutral"]
        + sell * _VOTE_WEIGHTS["sell"]
        + strong_sell * _VOTE_WEIGHTS["strong_sell"]
    )
    score = weighted / (total * 2.0)  # normalize to -1..+1
    return rating_from_score(score)


def direction_from_rating(rating: str | None) -> str | None:
    """Collapses the 5-level rating down to the simpler buy/hold/sell
    vocabulary ``ExternalSignal.direction``/strategy vote-counting already
    expects (e.g. ``signal_follow.min_buy_votes``)."""
    if rating in ("strong_buy", "buy"):
        return "buy"
    if rating == "neutral":
        return "hold"
    if rating in ("sell", "strong_sell"):
        return "sell"
    return None


__all__ = [
    "RATING_LEVELS",
    "direction_from_rating",
    "rating_from_score",
    "rating_from_text",
    "rating_from_vote_counts",
]
