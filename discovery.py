import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

from config import PAGES_PER_QUERY, RECENT_DAYS, SEARCH_QUERIES, TARGET_CANDIDATES
from db import get_conn, init_db

load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")
SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def search_videos(query, page_token=None):
    """One page (50 results) of recent videos. Video search surfaces smaller,
    active creators; channel search mostly returns big brands."""
    published_after = (datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": 50,
        "publishedAfter": published_after,
        "relevanceLanguage": "en",
        "key": API_KEY,
    }
    if page_token:
        params["pageToken"] = page_token
    res = requests.get(SEARCH_URL, params=params, timeout=20)
    res.raise_for_status()
    return res.json()


def discover():
    init_db()
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM influencers").fetchone()[0]

    for query in SEARCH_QUERIES:
        if total >= TARGET_CANDIDATES:
            break
        page_token = None
        for _ in range(PAGES_PER_QUERY):
            try:
                data = search_videos(query, page_token)
            except requests.RequestException as e:
                print(f"API error on '{query}': {e}")
                break

            for item in data.get("items", []):
                ch_id = item["snippet"]["channelId"]
                cur = conn.execute(
                    "INSERT OR IGNORE INTO influencers (channel_id, name, profile_url, discovered_via) "
                    "VALUES (?, ?, ?, ?)",
                    (ch_id, item["snippet"]["channelTitle"], f"https://www.youtube.com/channel/{ch_id}", query),
                )
                total += cur.rowcount   # 0 when the channel was already stored
            conn.commit()

            page_token = data.get("nextPageToken")
            if not page_token or total >= TARGET_CANDIDATES:
                break
        print(f"'{query}' done -> total channels: {total}")

    conn.close()
    print(f"\nDiscovery complete: {total} unique channels")


if __name__ == "__main__":
    discover()
