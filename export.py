import csv
import os

from config import NICHE
from db import get_conn, init_db

OUT = "output"


def write_csv(filename, rows):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, filename)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:   # BOM so Excel reads Unicode
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    print(f"{path}  ({len(rows)} rows)")


def na(value, text="Not Available"):
    return text if value in (None, "") else value


def export():
    init_db()
    conn = get_conn()

    dataset = []
    for r in conn.execute("SELECT * FROM influencers ORDER BY filter_status DESC, name"):
        dataset.append({
            "Name": r["name"],
            "Platform": r["platform"],
            "Followers": "Hidden by creator" if r["subscribers_hidden"] else na(r["subscribers"]),
            "Engagement Rate (%)": na(r["engagement_rate"]),
            "Niche": NICHE,
            "Email": na(r["email"], "Not Found"),
            "Profile URL": r["profile_url"],
            "Content Themes": na(r["content_themes"]),
            "Instagram": na(r["instagram"], "Not Found"),
            "Website": na(r["website"], "Not Found"),
            "Country": na(r["country"]),
            "Audience Age": "Not Available",   # not exposed by the public YouTube API
            "Audience Gender": "Not Available",
            "Last Upload (days ago)": na(r["days_since_upload"]),
            "Fitness Relevance": na(r["relevance_score"]),
            "Status": na(r["filter_status"], "Not Filtered"),
            "Reason": na(r["filter_reason"], ""),
        })
    write_csv("influencer_dataset.csv", dataset)
    write_csv("shortlisted_influencers.csv", [d for d in dataset if d["Status"] == "PASS"])

    messages = [{
        "Influencer": r["name"],
        "Email": na(r["email"], "Not Found"),
        "Instagram": na(r["instagram"], "Not Found"),
        "Collab Angle": r["collab_angle"],
        "Email Subject": r["email_subject"],
        "Email Pitch": r["email_body"],
        "Email Words": r["email_words"],
        "Instagram DM": r["instagram_dm"],
        "DM Words": r["dm_words"],
    } for r in conn.execute("""
        SELECT i.name, i.email, i.instagram, m.* FROM messages m
        JOIN influencers i ON i.channel_id = m.channel_id ORDER BY i.name""")]
    write_csv("personalized_messages.csv", messages)

    tracker = [{
        "Influencer": r["name"],
        "Channel": r["channel"],
        "Email / Handle": r["recipient"],
        "Delivered To": "Test inbox" if r["delivered_to"] and r["delivered_to"] != r["recipient"] else na(r["delivered_to"], ""),
        "Message Generated": "Yes",
        "Sent": {"sent": "Yes", "sent_manual": "Yes", "simulated": "Simulated"}.get(r["status"], "No"),
        "Date": r["created_at"],
        "Status": r["status"],
        "Error": na(r["error"], ""),
    } for r in conn.execute("""
        SELECT i.name, o.* FROM outreach_log o
        JOIN influencers i ON i.channel_id = o.channel_id ORDER BY o.channel, i.name""")]
    write_csv("outreach_tracker.csv", tracker)

    conn.close()


if __name__ == "__main__":
    export()