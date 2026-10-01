from collections import Counter

from config import (ALLOWED_COUNTRIES, BLOCKLIST, MAX_DAYS_SINCE_UPLOAD, MAX_SUBSCRIBERS,
                    MIN_ENGAGEMENT, MIN_RELEVANCE, MIN_SUBSCRIBERS)
from db import get_conn, init_db


def check(inf):
    """Returns a list of (rule, reason) failures. Empty list = PASS."""
    if inf["error"]:
        return [("enrichment", f"Could not enrich: {inf['error']}")]

    fails = []

    subs = inf["subscribers"]
    if subs is None:
        fails.append(("followers", "Subscriber count hidden"))
    elif subs < MIN_SUBSCRIBERS:
        fails.append(("followers", f"Followers {subs:,} < {MIN_SUBSCRIBERS:,}"))
    elif subs > MAX_SUBSCRIBERS:
        fails.append(("followers", f"Followers {subs:,} > {MAX_SUBSCRIBERS:,} (not micro)"))

    er = inf["engagement_rate"]
    if er is None:
        fails.append(("engagement", "Engagement unavailable (likes hidden)"))
    elif er < MIN_ENGAGEMENT:
        fails.append(("engagement", f"Engagement {er}% < {MIN_ENGAGEMENT}%"))

    days = inf["days_since_upload"]
    if days is None:
        fails.append(("activity", "No uploads found"))
    elif days > MAX_DAYS_SINCE_UPLOAD:
        fails.append(("activity", f"Inactive: last upload {days} days ago"))

    rel = inf["relevance_score"] or 0
    if rel < MIN_RELEVANCE:
        fails.append(("relevance", f"Low fitness relevance ({rel})"))

    if ALLOWED_COUNTRIES and inf["country"] and inf["country"] not in ALLOWED_COUNTRIES:
        fails.append(("geography", f"Country {inf['country']} not targeted"))

    text = ((inf["description"] or "") + " " + (inf["recent_titles"] or "")).lower()
    bad = [w for w in BLOCKLIST if w in text]
    if bad:
        fails.append(("brand_safety", f"Brand-safety flag: {', '.join(bad)}"))

    return fails


def run_filters():
    init_db()
    conn = get_conn()
    rows = conn.execute("SELECT * FROM influencers WHERE enriched = 1").fetchall()
    passed, fail_counts = 0, Counter()

    for inf in rows:
        fails = check(inf)
        if fails:
            status, reason = "FAIL", "; ".join(r for _, r in fails)
            fail_counts.update(rule for rule, _ in fails)
        else:
            status, reason = "PASS", "Meets all criteria"
            if inf["email"] == "Not Found":
                reason += " (no public email - DM/manual outreach only)"
            passed += 1
        conn.execute("UPDATE influencers SET filter_status = ?, filter_reason = ? WHERE channel_id = ?",
                     (status, reason, inf["channel_id"]))
    conn.commit()

    with_email = conn.execute(
        "SELECT COUNT(*) FROM influencers WHERE filter_status = 'PASS' AND email != 'Not Found'").fetchone()[0]
    print(f"PASS: {passed} | FAIL: {len(rows) - passed} | PASS with email: {with_email}")
    print("Fail reasons:", dict(fail_counts.most_common()))
    conn.close()


if __name__ == "__main__":
    run_filters()
