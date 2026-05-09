"""
Telegram inline keyboard callback_data constants.
Format: {flow}:{action}:{value}
Max 64 bytes per Telegram spec.
"""

# ── Onboarding flow ──────────────────────────────────────────────────────────
ONB_TICKERS_SAMPLE = "onb:tickers:sample"
ONB_THRESHOLD_DEFAULT = "onb:threshold:default"
ONB_THRESHOLD_CUSTOM = "onb:threshold:custom"
ONB_THRESHOLD_SKIP = "onb:threshold:skip"
ONB_QUIET_DEFAULT = "onb:quiet:default"
ONB_QUIET_CUSTOM = "onb:quiet:custom"
ONB_QUIET_NEVER = "onb:quiet:never"
ONB_CANCEL = "onb:cancel"

# ── Watchlist dashboard ───────────────────────────────────────────────────────
WL_ADD = "wl:add"
WL_REMOVE_START = "wl:remove:start"
WL_THRESHOLD_EDIT = "wl:threshold:edit"
WL_QUIET_EDIT = "wl:quiet:edit"
WL_BACK = "wl:back"
WL_CANCEL_ACTION = "wl:cancel_action"   # cancel any pending WL pending-action prompt


def wl_remove(ticker: str) -> str:
    return f"wl:remove:{ticker[:10]}"


def wl_threshold_set(ticker: str) -> str:
    return f"wl:thr:set:{ticker[:8]}"


# ── Alert actions ─────────────────────────────────────────────────────────────
def alert_snooze(ticker: str, hours: int) -> str:
    return f"alert:snooze:{ticker[:8]}:{hours}h"


ALERT_SOURCE = "alert:source"
ALERT_DEEPDIVE_START = "alert:deepdive"


# ── Replace / append watchlist ────────────────────────────────────────────────
WL_REPLACE_CONFIRM = "wl:replace:yes"
WL_APPEND_CONFIRM = "wl:replace:append"
WL_REPLACE_CANCEL = "wl:replace:cancel"
