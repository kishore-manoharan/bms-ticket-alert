"""Central configuration for the BookMyShow ticket alert."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    movie_name: str = "the-odyssey"
    movie_code: str = "ET00452034"
    region_code: str = "CHEN"  # BookMyShow's Chennai region code.
    target_date: str = "20260722"  # YYYYMMDD
    theatres: tuple[str, ...] = (
        "AGS Cinemas OMR Navlur",
        "INOX LUXE Phoenix Market City, Velachery",
    )
    bot_token: str = os.environ.get("BOT_TOKEN", "")
    chat_id: str = os.environ.get("CHAT_ID", "")
    state_file: Path = Path(os.environ.get("STATE_FILE", ".state/bms_notification_state.json"))
    timeout_seconds: int = 45
    # This is a public movie/showtime URL, pinned to the movie and date.
    showtime_url: str = "https://in.bookmyshow.com/movies/chennai/jana-nayagan/buytickets/ET00430817/20260724"
    # Undocumented BookMyShow JSON endpoint. Kept as a best-effort fast path.
    api_url: str = "https://in.bookmyshow.com/pwa/api/de/showtimes/byevent"

    @property
    def api_params(self) -> dict[str, str]:
        return {
            "regionCode": self.region_code,
            "subCode": "",
            "eventCode": self.movie_code,
            "dateCode": self.target_date,
        }


SETTINGS = Settings()
