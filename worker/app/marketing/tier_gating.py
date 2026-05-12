"""Sprint 4 feature gating — what a given Pro tier can see.

Stored on User.proTier (null | 'watch' | 'pro' | 'desk'). Frontend +
backend both consult `can_user_see(tier, feature)` instead of hard-coded
tier checks scattered through the code.

Adding a new feature: add it to TIER_FEATURES under the lowest tier
that should have it. Higher tiers automatically inherit via the
union pattern below.
"""
from __future__ import annotations

from typing import Optional

# Tier names (None / null on User means free).
TIER_FREE = "free"
TIER_WATCH = "watch"
TIER_PRO = "pro"
TIER_DESK = "desk"

ALL_TIERS = (TIER_FREE, TIER_WATCH, TIER_PRO, TIER_DESK)

# Feature membership per tier. Higher tiers inherit lower-tier features
# via the inheritance chain in `_features_for_tier`.
_WATCH_ONLY: frozenset[str] = frozenset({
    "watchlist_basic",
    "state_alerts",
    "quiet_hours",
})

_PRO_ONLY: frozenset[str] = frozenset({
    "divergence_compass",
    "sector_context",
    "weekly_digest",
    "honest_miss_log",
    "custom_notification_mode",
    "pdf_export",
    "share_cards",
    "pre_earnings_smart_muting",
    "priority_email_reply",
})

_DESK_ONLY: frozenset[str] = frozenset({
    "deck_analyst_briefings",
    "private_telegram_channel",
})

TIER_INHERITANCE: dict[str, tuple[str, ...]] = {
    TIER_FREE: (),
    TIER_WATCH: (TIER_WATCH,),
    TIER_PRO: (TIER_WATCH, TIER_PRO),
    TIER_DESK: (TIER_WATCH, TIER_PRO, TIER_DESK),
}

_TIER_FEATURE_BLOCKS: dict[str, frozenset[str]] = {
    TIER_WATCH: _WATCH_ONLY,
    TIER_PRO: _PRO_ONLY,
    TIER_DESK: _DESK_ONLY,
}


def _features_for_tier(tier: str) -> frozenset[str]:
    """Union of feature sets inherited by `tier`."""
    out: set[str] = set()
    for chain_tier in TIER_INHERITANCE.get(tier, ()):
        out.update(_TIER_FEATURE_BLOCKS.get(chain_tier, frozenset()))
    return frozenset(out)


def can_user_see(tier: Optional[str], feature: str) -> bool:
    """Return True when the given tier unlocks `feature`.

    `tier=None` → free user. Unknown tiers are treated as free (safe default).
    Unknown features always return False (closed by default).
    """
    resolved = (tier or TIER_FREE).lower()
    if resolved not in ALL_TIERS:
        resolved = TIER_FREE
    return feature in _features_for_tier(resolved)


def watchlist_limit_for_tier(tier: Optional[str]) -> int:
    """Hard caps so frontend can enforce on add-ticker. Free=0, Watch=5,
    Pro=15, Desk=50."""
    return {
        TIER_FREE: 0,
        TIER_WATCH: 5,
        TIER_PRO: 15,
        TIER_DESK: 50,
    }.get((tier or TIER_FREE).lower(), 0)
