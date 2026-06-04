from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

from bookmarks_organizer.db import Database
from bookmarks_organizer.models import SyncSummary, TweetRecord
from bookmarks_organizer.search import SearchService


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _extract_tweet_id(url: str) -> str | None:
    match = re.search(r"/status/(\d+)", url)
    if not match:
        return None
    return match.group(1)


class BookmarkSyncService:
    def __init__(
        self,
        db: Database,
        search_service: SearchService,
        *,
        browser_profile_dir: str,
        headless: bool,
        max_scrolls: int,
        max_batch: int,
        login_wait_seconds: int,
    ) -> None:
        self.db = db
        self.search_service = search_service
        self.browser_profile_dir = browser_profile_dir
        self.headless = headless
        self.max_scrolls = max_scrolls
        self.max_batch = max_batch
        self.login_wait_seconds = login_wait_seconds

    async def sync_new_bookmarks(self) -> SyncSummary:
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise RuntimeError(
                "Playwright is not installed in the environment. Run `uv sync` and "
                "`uv run playwright install chromium` first."
            ) from exc

        state = self.db.get_sync_state()
        latest_known = state.get("latest_bookmark_id") or None
        new_items: list[TweetRecord] = []
        stopped_on_existing = False

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=self.browser_profile_dir,
                headless=self.headless,
                viewport={"width": 1440, "height": 1024},
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://x.com/i/bookmarks", wait_until="networkidle")

            if "login" in page.url.lower():
                await asyncio.sleep(self.login_wait_seconds)
                await page.goto("https://x.com/i/bookmarks", wait_until="networkidle")

            seen_ids: set[str] = set()
            previous_height = 0
            for _ in range(self.max_scrolls):
                await page.wait_for_timeout(1250)
                articles = await page.locator("article").evaluate_all(
                    """
                    (nodes) => nodes.map((node) => {
                      const link = node.querySelector('a[href*="/status/"]');
                      const time = node.querySelector('time');
                      const textNode = node.querySelector('[data-testid="tweetText"]');
                      const authorNode = node.querySelector('[data-testid="User-Name"]');
                      const authorText = authorNode ? authorNode.innerText.split('\\n') : [];
                      return {
                        url: link ? link.href : null,
                        createdAt: time ? time.getAttribute('datetime') : null,
                        text: textNode ? textNode.innerText : '',
                        author: authorText[0] || 'Unknown',
                        handle: authorText.find((part) => part.startsWith('@')) || '@unknown',
                      };
                    })
                    """
                )
                for article in articles:
                    url = article.get("url")
                    if not url:
                        continue
                    tweet_id = _extract_tweet_id(url)
                    if not tweet_id or tweet_id in seen_ids:
                        continue
                    seen_ids.add(tweet_id)
                    if tweet_id == latest_known or self.db.tweet_exists(tweet_id):
                        stopped_on_existing = True
                        break
                    new_items.append(
                        TweetRecord(
                            tweet_id=tweet_id,
                            author=article.get("author") or "Unknown",
                            handle=article.get("handle") or "@unknown",
                            text=article.get("text") or "",
                            url=url,
                            created_at=_parse_datetime(article.get("createdAt")),
                            bookmarked_at=datetime.now(timezone.utc),
                        )
                    )
                    if len(new_items) >= self.max_batch:
                        break
                if stopped_on_existing or len(new_items) >= self.max_batch:
                    break
                current_height = await page.evaluate("document.body.scrollHeight")
                if current_height == previous_height:
                    break
                previous_height = current_height
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

            await context.close()

        for tweet in reversed(new_items):
            self.search_service.enrich_and_index(tweet)

        newest_id = new_items[0].tweet_id if new_items else latest_known
        synced_at = datetime.now(timezone.utc)
        self.db.set_sync_state(newest_id, synced_at)
        return SyncSummary(
            added_count=len(new_items),
            stopped_on_existing=stopped_on_existing,
            latest_bookmark_id=newest_id,
            synced_at=synced_at,
        )

