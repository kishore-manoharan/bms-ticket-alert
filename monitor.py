"""Watch one BookMyShow movie/date and notify exactly once for selected theatres.

The monitor tries BookMyShow's JSON showtime resource first.  Its schema is
validated by content rather than assumed.  When BookMyShow changes or blocks
that internal endpoint, Playwright captures JSON XHR/fetch responses while it
loads the official, date-specific page, then uses a narrow DOM fallback.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from collections.abc import Iterator
from typing import Any

import requests
from playwright.async_api import Page, Response, async_playwright
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from config import SETTINGS, Settings
from notifier import NotificationError, send_telegram
from state import read_state, save_notification

TIME_RE = re.compile(r"\b(?:[0-1]?\d|2[0-3]):[0-5]\d\s*(?:[AaPp]\.?[Mm]\.?)?\b")


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def walk_dicts(value: Any) -> Iterator[dict[str, Any]]:
    """Yield every JSON object; endpoint schemas can change without notice."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def as_text(value: Any) -> str:
    return " ".join(str(v) for v in value.values()) if isinstance(value, dict) else str(value)


def collect_times(value: Any) -> list[str]:
    """Extract time-looking values from an individual venue subtree."""
    found: set[str] = set()
    if isinstance(value, (dict, list)):
        source = json.dumps(value, ensure_ascii=False)
    else:
        source = str(value)
    for match in TIME_RE.finditer(source):
        found.add(re.sub(r"\s+", " ", match.group(0)).upper())
    return sorted(found)


def matches_from_payload(payload: Any, settings: Settings) -> dict[str, list[str]]:
    """Return only configured theatres that have at least one real show time."""
    found: dict[str, list[str]] = {}
    for item in walk_dicts(payload):
        # VenueName is used by the known legacy JSON response; also accept
        # current endpoint variants such as theatreName / cinema_name.
        candidate = " ".join(
            str(item.get(key, "")) for key in ("VenueName", "venueName", "theatreName", "theaterName", "cinemaName", "name")
        ).casefold()
        for theatre in settings.theatres:
            if theatre.casefold() in candidate:
                times = collect_times(item)
                if times:
                    found[theatre] = times
    return found


@retry(retry=retry_if_exception_type(requests.RequestException), wait=wait_exponential_jitter(initial=2, max=20), stop=stop_after_attempt(3), reraise=True)
def api_showtimes(settings: Settings) -> dict[str, list[str]]:
    """Use the internal JSON resource only when it returns valid JSON."""
    response = requests.get(
        settings.api_url,
        params=settings.api_params,
        headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
        timeout=settings.timeout_seconds,
    )
    response.raise_for_status()
    if "json" not in response.headers.get("content-type", "").lower():
        raise requests.RequestException("Internal endpoint did not return JSON")
    payload = response.json()
    matches = matches_from_payload(payload, settings)
    logging.info("JSON endpoint %s returned %d matching theatre(s)", response.url, len(matches))
    return matches


async def capture_json(response: Response, captured: list[tuple[str, Any]]) -> None:
    """Capture only JSON XHR/fetch responses; failures are expected on ads/CDNs."""
    if response.request.resource_type not in {"xhr", "fetch"}:
        return
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type.lower():
        return
    try:
        captured.append((response.url, await response.json()))
    except Exception as exc:  # network body may be unavailable after navigation
        logging.debug("Could not parse JSON response %s: %s", response.url, exc)


@retry(retry=retry_if_exception_type(Exception), wait=wait_exponential_jitter(initial=2, max=20), stop=stop_after_attempt(3), reraise=True)
async def playwright_showtimes(settings: Settings) -> dict[str, list[str]]:
    """Load the canonical showtime URL and inspect its JSON traffic first."""
    captured: list[tuple[str, Any]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page: Page = await browser.new_page(viewport={"width": 1440, "height": 1100})
        page.on("response", lambda response: asyncio.create_task(capture_json(response, captured)))
        try:
            await page.goto(settings.showtime_url, wait_until="domcontentloaded", timeout=settings.timeout_seconds * 1000)
            await page.wait_for_timeout(5_000)  # allow client-side showtime data to arrive
            await page.wait_for_timeout(500)    # let response handlers finish
            for url, payload in captured:
                matches = matches_from_payload(payload, settings)
                if matches:
                    logging.info("Discovered showtime JSON response: %s", url)
                    return matches

            # Last resort: never scan the whole document.  Limit extraction to
            # the closest venue card containing an exact configured name.
            matches: dict[str, list[str]] = {}
            for theatre in settings.theatres:
                label = page.get_by_text(theatre, exact=False).first
                if await label.count() == 0:
                    continue
                card = label.locator("xpath=ancestor-or-self::*[self::section or self::li or self::div][.//text()]").first
                text = await card.inner_text(timeout=5_000)
                times = sorted(set(TIME_RE.findall(text)))
                if times:
                    matches[theatre] = times
            return matches
        finally:
            await browser.close()


async def find_shows(settings: Settings) -> dict[str, list[str]]:
    try:
        return api_showtimes(settings)
    except Exception as exc:
        logging.warning("JSON fast path unavailable (%s); using Playwright network inspection", exc)
        return await playwright_showtimes(settings)


async def main() -> int:
    configure_logging()
    state = read_state(SETTINGS.state_file)
    if state.get("notification_sent"):
        logging.info("A notification was already sent at %s; exiting.", state.get("notified_at", "unknown"))
        return 0
    matches = await find_shows(SETTINGS)
    if not matches:
        logging.info("No configured theatre has showtimes for %s on %s.", SETTINGS.movie_name, SETTINGS.target_date)
        return 0
    lines = [f"Tickets are available: {SETTINGS.movie_name}", "Date: 24 July 2026"]
    lines.extend(f"• {theatre}: {', '.join(times)}" for theatre, times in matches.items())
    lines.append(SETTINGS.showtime_url)
    send_telegram(SETTINGS.bot_token, SETTINGS.chat_id, "\n".join(lines))
    save_notification(SETTINGS.state_file, list(matches), matches)
    logging.info("Notification sent and persisted for %s", list(matches))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except (NotificationError, requests.RequestException, Exception) as exc:
        logging.exception("Monitor failed: %s", exc)
        raise SystemExit(1)
