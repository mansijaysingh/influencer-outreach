import sqlite3

from config import DB_PATH

# Columns added to `influencers` after discovery (enrichment + filtering).
EXTRA_COLUMNS = {
    "subscribers": "INTEGER",
    "subscribers_hidden": "INTEGER DEFAULT 0",
    "video_count": "INTEGER",
    "country": "TEXT",
    "description": "TEXT",
    "recent_titles": "TEXT",
    "avg_views": "REAL",
    "engagement_rate": "REAL",
    "days_since_upload": "INTEGER",
    "email": "TEXT",
    "instagram": "TEXT",
    "website": "TEXT",
    "content_themes": "TEXT",
    "relevance_score": "REAL",
    "enriched": "INTEGER DEFAULT 0",
    "error": "TEXT",
    "filter_status": "TEXT",
    "filter_reason": "TEXT",
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS influencers (
            channel_id     TEXT PRIMARY KEY,
            name           TEXT,
            platform       TEXT DEFAULT 'YouTube',
            profile_url    TEXT,
            discovered_via TEXT
        )
    """)
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(influencers)")}
    for col, col_type in EXTRA_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE influencers ADD COLUMN {col} {col_type}")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            channel_id    TEXT PRIMARY KEY,
            collab_angle  TEXT,
            email_subject TEXT,
            email_body    TEXT,
            email_words   INTEGER,
            instagram_dm  TEXT,
            dm_words      INTEGER,
            attempts      INTEGER,
            generated_at  TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS outreach_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id    TEXT,
            channel       TEXT,      -- email | instagram_dm
            recipient     TEXT,
            delivered_to  TEXT,
            status        TEXT,      -- simulated | sent | failed | pending_manual | sent_manual
            error         TEXT,
            created_at    TEXT,
            UNIQUE(channel_id, channel)
        )
    """)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database ready")
