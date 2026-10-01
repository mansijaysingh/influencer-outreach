import json
import os
import re
from collections import Counter
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from config import NICHE_KEYWORDS, RECENT_VIDEOS
from db import get_conn, init_db

load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")
BASE = "https://www.googleapis.com/youtube/v3"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SOCIAL_DOMAINS = ("youtube", "youtu.be", "instagram", "tiktok", "facebook", "twitter", "x.com",
                  "amzn", "amazon", "bit.ly", "linktr.ee", "wa.me", "t.me", "spotify", "discord")
STOPWORDS = set("""a an the and or of to in on for with my your how what why this that is are you i
me we at from by it new best full day days week min minute minutes vs video shorts part ep do get
no not can will 2024 2025 2026 trending viral shorts fyp""".split())


def safe_error(e):
    """Error text without the API key (requests puts the full URL in its messages)."""
    return re.sub(r"key=[^&\s'\"]+", "key=***", str(e))[:300]


def yt_get(endpoint, **params):
    params["key"] = API_KEY
    res = requests.get(f"{BASE}/{endpoint}", params=params, timeout=20)
    res.raise_for_status()
    return res.json()


def find_email(texts):
    """First real email in the descriptions. Handles 'name [at] gmail [dot] com'.
    Returns 'Not Found' instead of guessing."""
    for text in texts:
        text = re.sub(r"\s*[\[\(]\s*at\s*[\]\)]\s*", "@", text or "", flags=re.I)
        text = re.sub(r"\s*[\[\(]\s*dot\s*[\]\)]\s*", ".", text, flags=re.I)
        for email in EMAIL_RE.findall(text):
            email = email.lower().strip(".")
            if email.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")) or "example.com" in email:
                continue
            return email
    return "Not Found"


def find_instagram(text):
    m = re.search(r"instagram\.com/([A-Za-z0-9_.]{2,30})", text or "", re.I)
    if m and m.group(1).lower() not in ("p", "reel", "reels", "explore", "stories"):
        return "https://www.instagram.com/" + m.group(1).rstrip(".")
    return None


def find_website(text):
    for url in re.findall(r"https?://[^\s<>\"')]+", text or ""):
        if not any(d in url.lower() for d in SOCIAL_DOMAINS):
            return url.rstrip(".,")
    return None


def to_int(value):
    return int(value) if value is not None else None


def engagement_rate(videos):
    """(likes + comments) / views * 100, skipping videos with hidden likes."""
    usable = [v for v in videos if v["views"] and v["likes"] is not None]
    if not usable:
        return None
    interactions = sum(v["likes"] + v["comments"] for v in usable)
    views = sum(v["views"] for v in usable)
    return round(interactions / views * 100, 2)


def days_since(published_at):
    dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).days


def relevance_score(titles):
    """Share (0-1) of recent titles that contain a niche keyword."""
    if not titles:
        return 0.0
    hits = sum(1 for t in titles if any(k in t.lower() for k in NICHE_KEYWORDS))
    return round(hits / len(titles), 2)


def _top_phrases(texts, n):
    counts = Counter()
    for t in texts:
        words = [w for w in re.findall(r"[a-z]+", t.lower()) if w not in STOPWORDS and len(w) > 2]
        counts.update(words)
        counts.update(f"{a} {b}" for a, b in zip(words, words[1:]))
    # 2-word phrases get a boost so "home workout" beats "home" + "workout"
    ranked = sorted(((c * (1.5 if " " in p else 1), p) for p, c in counts.items() if c >= 2), reverse=True)
    themes = []
    for _, phrase in ranked:
        if not any(phrase in t or t in phrase for t in themes):
            themes.append(phrase)
        if len(themes) == n:
            break
    return themes


def content_themes(titles, n=4):
    """Most frequent words/phrases in recent titles. Falls back to hashtags
    when titles are mostly tags (common for Shorts)."""
    themes = _top_phrases([re.sub(r"#\w+", "", t) for t in titles], n)
    if not themes:
        themes = _top_phrases([" ".join(re.findall(r"#(\w+)", t)) for t in titles], n)
    return ", ".join(themes) if themes else "Not enough data"


def enrich_channel(ch):
    stats, snippet = ch["statistics"], ch["snippet"]
    hidden = stats.get("hiddenSubscriberCount", False)
    description = snippet.get("description", "")

    uploads_id = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    items = yt_get("playlistItems", part="contentDetails", playlistId=uploads_id,
                   maxResults=RECENT_VIDEOS).get("items", [])
    video_ids = [it["contentDetails"]["videoId"] for it in items]
    raw = yt_get("videos", part="snippet,statistics", id=",".join(video_ids)).get("items", []) if video_ids else []

    videos = [{
        "title": v["snippet"]["title"],
        "description": v["snippet"].get("description", ""),
        "published_at": v["snippet"]["publishedAt"],
        "views": to_int(v["statistics"].get("viewCount")) or 0,
        "likes": to_int(v["statistics"].get("likeCount")),   # None when hidden
        "comments": to_int(v["statistics"].get("commentCount")) or 0,
    } for v in raw]
    videos.sort(key=lambda v: v["published_at"], reverse=True)
    titles = [v["title"] for v in videos]
    all_text = [description] + [v["description"] for v in videos]

    return {
        "name": snippet["title"],
        "profile_url": "https://www.youtube.com/" + snippet["customUrl"] if snippet.get("customUrl") else None,
        "subscribers": None if hidden else to_int(stats.get("subscriberCount")),
        "subscribers_hidden": int(hidden),
        "video_count": to_int(stats.get("videoCount")),
        "country": snippet.get("country"),
        "description": description,
        "recent_titles": json.dumps(titles, ensure_ascii=False),
        "avg_views": round(sum(v["views"] for v in videos) / len(videos), 1) if videos else None,
        "engagement_rate": engagement_rate(videos),
        "days_since_upload": days_since(videos[0]["published_at"]) if videos else None,
        "email": find_email(all_text),
        "instagram": find_instagram(" ".join(all_text)),
        "website": find_website(description),
        "content_themes": content_themes(titles),
        "relevance_score": relevance_score(titles),
        "enriched": 1,
        "error": None,
    }


def save(conn, channel_id, data):
    if data.get("profile_url") is None:
        data.pop("profile_url", None)   # keep the /channel/ URL from discovery
    cols = ", ".join(f"{k} = ?" for k in data)
    conn.execute(f"UPDATE influencers SET {cols} WHERE channel_id = ?", (*data.values(), channel_id))
    conn.commit()


def enrich():
    init_db()
    conn = get_conn()
    ids = [r["channel_id"] for r in conn.execute("SELECT channel_id FROM influencers WHERE enriched = 0")]
    print(f"Enriching {len(ids)} channels...")

    for i in range(0, len(ids), 50):   # channels.list accepts up to 50 IDs per call
        batch = ids[i:i + 50]
        try:
            channels = yt_get("channels", part="snippet,statistics,contentDetails",
                              id=",".join(batch)).get("items", [])
        except requests.RequestException as e:
            print(f"Batch failed, will retry on next run: {safe_error(e)}")
            continue
        returned = {c["id"] for c in channels}

        for ch in channels:
            try:
                save(conn, ch["id"], enrich_channel(ch))
                print(f"  OK   {ch['snippet']['title']}")
            except requests.RequestException as e:
                # network/API hiccup: leave enriched = 0 so the next run retries it
                print(f"  RETRY LATER {ch['snippet']['title']}: {safe_error(e)}")
            except Exception as e:
                save(conn, ch["id"], {"enriched": 1, "error": safe_error(e)})
                print(f"  FAIL {ch['snippet']['title']}: {safe_error(e)}")

        for missing in set(batch) - returned:
            save(conn, missing, {"enriched": 1, "error": "Channel not returned by API (deleted or private)"})

    total = conn.execute("SELECT COUNT(*) FROM influencers WHERE enriched = 1").fetchone()[0]
    emails = conn.execute("SELECT COUNT(*) FROM influencers WHERE email IS NOT NULL AND email != 'Not Found'").fetchone()[0]
    errors = conn.execute("SELECT COUNT(*) FROM influencers WHERE error IS NOT NULL").fetchone()[0]
    print(f"\nEnriched: {total} | Emails found: {emails} | Errors: {errors}")
    conn.close()


def refresh_themes():
    """Recompute content themes from stored titles (no API calls)."""
    init_db()
    conn = get_conn()
    rows = conn.execute("SELECT channel_id, recent_titles FROM influencers WHERE recent_titles IS NOT NULL").fetchall()
    for r in rows:
        conn.execute("UPDATE influencers SET content_themes = ? WHERE channel_id = ?",
                     (content_themes(json.loads(r["recent_titles"])), r["channel_id"]))
    conn.commit()
    conn.close()
    print(f"Refreshed themes for {len(rows)} channels")


if __name__ == "__main__":
    # python enrichment.py                    enrich new channels
    # python enrichment.py --refresh-themes   recompute themes only
    import sys
    refresh_themes() if "--refresh-themes" in sys.argv else enrich()
