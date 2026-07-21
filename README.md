# BookMyShow ticket alert

Monitors **Jana Nayagan** in Chennai on **24 July 2026** and sends exactly one Telegram alert when either configured theatre lists a real show time:

- AGS Cinemas OMR Navlur
- INOX LUXE Phoenix Market City, Velachery

It never alerts for another movie or theatre. The target page is pinned to the movie code `ET00430817` and date `20260724`:

`https://in.bookmyshow.com/movies/chennai/jana-nayagan/buytickets/ET00430817/20260724`

## Setup

1. Create a Telegram bot with BotFather and get your chat ID.
2. Add repository secrets `BOT_TOKEN` and `CHAT_ID`.
3. Push this directory as the repository root and enable Actions.
4. Run **Check BookMyShow tickets** manually once to validate the secrets.

For local use:

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python -m playwright install chromium
export BOT_TOKEN=... CHAT_ID=...  # PowerShell: $env:BOT_TOKEN='...'
python monitor.py
```

## How it obtains showtimes

The monitor uses JSON before HTML. Its first, best-effort request is the undocumented BookMyShow resource:

```
GET https://in.bookmyshow.com/pwa/api/de/showtimes/byevent
  ?regionCode=CHEN&subCode=&eventCode=ET00430817&dateCode=20260724
```

The legacy response shape is `BookMyShow.ShowDetails[].Venues[]`; a venue has `VenueName` and nested show fields. The code treats that as an untrusted schema, locates only configured venue names, and extracts time values from that venue's subtree. The parameters mean `eventCode` = movie, `regionCode` = city, `dateCode` = date, while each `Venues[]` entry represents a theatre plus its shows/times.

This endpoint was documented in an older public BookMyShow monitor, so it is not treated as a stable public contract. A live direct request from this environment could not reach BookMyShow, so do not assume this endpoint is currently available. Each execution therefore falls back to Playwright: it opens the official date-specific URL, captures only `fetch`/`XHR` JSON responses, examines their payloads for the two exact theatres and associated show times, and logs the discovered response URL. If BookMyShow serves all data server-side, it uses a tightly scoped venue-card selector as a final fallback.

This is more resilient than page-wide HTML scraping: structured payloads preserve movie/date/venue relationships, avoid presentation-only markup, and are less affected by CSS/layout changes. The fallback keeps the monitor useful when BookMyShow changes or blocks its internal endpoint.

## Reliability notes

- Network and Playwright operations retry three times with exponential jitter.
- Detailed timestamped logs go to Actions output.
- `.state/bms_notification_state.json` is atomically written only after Telegram accepts the message. The workflow commits it with `GITHUB_TOKEN`, surviving separate scheduled runs and preventing duplicate alerts.
- GitHub Actions schedules are best-effort and can be delayed under platform load; the cron expression requests every five minutes.
- GitHub-hosted runners may be geo-blocked by BookMyShow. If that happens, use a self-hosted runner located in India; the code and workflow do not bypass access controls.

## Changing the next monitor

Edit `Settings` in `config.py`: change the movie code/slug, `target_date`, `region_code`, `showtime_url`, and theatre names. Delete the persisted state file only when deliberately starting a new alert campaign.
