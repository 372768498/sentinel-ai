"""tweepy wrapper for X (Twitter) API v2.

Posting uses OAuth 1.0a User Context (4 keys: API key/secret + access token/secret).
Reading uses OAuth 2.0 App-only Bearer Token.

Default dry_run=True; flip with X_DRY_RUN=false in env.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PostResult:
    posted: bool
    tweet_id: Optional[str]
    text: str
    dry_run: bool
    error: Optional[str] = None


def _coerce_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class XClient:
    """tweepy.Client wrapper. Async-friendly wrappers run sync calls in a thread.

    Read-only ops only need bearer_token. Write ops need all 4 OAuth 1.0a keys.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        access_token_secret: Optional[str] = None,
        bearer_token: Optional[str] = None,
        dry_run: Optional[bool] = None,
    ):
        env_dry = os.environ.get("X_DRY_RUN")
        self.dry_run = dry_run if dry_run is not None else _coerce_bool(env_dry, default=True)

        self.api_key = api_key or os.environ.get("X_API_KEY", "").strip() or None
        self.api_secret = api_secret or os.environ.get("X_API_SECRET", "").strip() or None
        self.access_token = access_token or os.environ.get("X_ACCESS_TOKEN", "").strip() or None
        self.access_token_secret = (
            access_token_secret or os.environ.get("X_ACCESS_TOKEN_SECRET", "").strip() or None
        )
        self.bearer_token = bearer_token or os.environ.get("X_BEARER_TOKEN", "").strip() or None

        self._client = None

    def _can_post(self) -> bool:
        return all((self.api_key, self.api_secret, self.access_token, self.access_token_secret))

    def _build_client(self):
        if self._client is not None:
            return self._client
        import tweepy

        self._client = tweepy.Client(
            bearer_token=self.bearer_token,
            consumer_key=self.api_key,
            consumer_secret=self.api_secret,
            access_token=self.access_token,
            access_token_secret=self.access_token_secret,
            wait_on_rate_limit=False,
        )
        return self._client

    async def login(self, **_ignored) -> None:
        """Compatibility shim — tweepy is keyless-init, no session step needed.

        Kept for code that already calls XClient().login(); also validates that
        the 4 OAuth keys are present when not in dry-run.
        """
        if self.dry_run:
            logger.info("[DRY] X login skipped (dry_run=True)")
            return
        if not self._can_post():
            raise RuntimeError(
                "OAuth 1.0a keys missing. Need X_API_KEY / X_API_SECRET / "
                "X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET in env."
            )
        self._build_client()
        logger.info("X tweepy client ready (OAuth 1.0a)")

    async def post(self, text: str) -> PostResult:
        if self.dry_run:
            logger.info("[DRY] would post (%d chars): %s", len(text), text[:80].replace("\n", " "))
            return PostResult(posted=False, tweet_id=None, text=text, dry_run=True)

        if not self._can_post():
            return PostResult(
                posted=False,
                tweet_id=None,
                text=text,
                dry_run=False,
                error="missing_oauth_keys",
            )

        import asyncio

        client = self._build_client()
        loop = asyncio.get_running_loop()
        try:
            response = await loop.run_in_executor(None, lambda: client.create_tweet(text=text))
            tweet_id = str(response.data.get("id")) if response and response.data else None
            return PostResult(posted=bool(tweet_id), tweet_id=tweet_id, text=text, dry_run=False)
        except Exception as exc:
            logger.exception("X post failed")
            return PostResult(
                posted=False,
                tweet_id=None,
                text=text,
                dry_run=False,
                error=str(exc),
            )

    async def search(
        self, query: str, *, max_results: int = 20
    ) -> list[dict]:
        """Recent search via Bearer Token (read-only). Returns simplified dicts."""
        if self.dry_run:
            logger.info("[DRY] would search: %s", query)
            return []
        if not self.bearer_token:
            logger.warning("X search skipped: no bearer token")
            return []

        import asyncio

        client = self._build_client()
        loop = asyncio.get_running_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: client.search_recent_tweets(
                    query=query,
                    max_results=max(10, min(max_results, 100)),
                    tweet_fields=["created_at", "public_metrics", "author_id"],
                ),
            )
        except Exception as exc:
            logger.warning("X search failed: %s", exc)
            return []

        if not response or not response.data:
            return []
        return [
            {
                "id": str(t.id),
                "text": t.text,
                "author_id": str(t.author_id) if t.author_id else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "metrics": t.public_metrics or {},
            }
            for t in response.data
        ]
