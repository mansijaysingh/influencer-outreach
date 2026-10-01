import os
import re
import smtplib
import sys
import time
from datetime import datetime
from email.message import EmailMessage

from dotenv import load_dotenv

from config import BRAND, DAILY_LIMIT, SECONDS_BETWEEN_EMAILS, TEST_RECIPIENT
from db import get_conn, init_db

load_dotenv()
EMAIL_RE = re.compile(r"^[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}$")


def log(conn, channel_id, channel, recipient, status, delivered_to=None, error=None):
    """Upsert into outreach_log (one row per creator per channel)."""
    conn.execute("""
        INSERT INTO outreach_log (channel_id, channel, recipient, delivered_to, status, error, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(channel_id, channel) DO UPDATE SET
            status = excluded.status, delivered_to = excluded.delivered_to,
            error = excluded.error, created_at = excluded.created_at
    """, (channel_id, channel, recipient, delivered_to, status, error, datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def already_contacted(conn, channel_id, email, real_send):
    """True if this creator or this address was already emailed.
    Dry-run ('simulated') rows do not block a real send."""
    blocking = ("sent",) if real_send else ("sent", "simulated")
    marks = ",".join("?" * len(blocking))
    row = conn.execute(f"""
        SELECT 1 FROM outreach_log
        WHERE channel = 'email' AND status IN ({marks})
          AND (channel_id = ? OR lower(recipient) = lower(?))
    """, (*blocking, channel_id, email)).fetchone()
    return row is not None


def sent_today(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM outreach_log WHERE channel = 'email' AND status = 'sent' "
        "AND date(created_at) = date('now', 'localtime')").fetchone()[0]


def build_email(msg, to_addr):
    em = EmailMessage()
    em["Subject"] = msg["email_subject"]
    em["From"] = os.getenv("SMTP_USER", "demo@localhost")
    em["To"] = to_addr
    em.set_content(
        f"{msg['email_body']}\n\nBest,\n{BRAND['sender_name']}\n{BRAND['sender_title']}, {BRAND['name']}"
        "\n\n--\nNot interested? Just reply 'no thanks' and we won't contact you again."
    )
    return em


def send_emails(real_send=False):
    init_db()
    conn = get_conn()
    rows = conn.execute("""
        SELECT i.channel_id, i.name, i.email, m.email_subject, m.email_body
        FROM influencers i JOIN messages m ON i.channel_id = m.channel_id
        WHERE i.filter_status = 'PASS'
    """).fetchall()

    smtp = None
    if real_send:
        try:
            smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30)
            smtp.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
        except (smtplib.SMTPException, OSError) as e:
            print(f"SMTP login failed, nothing sent: {e}")
            conn.close()
            return

    stats = {"sent": 0, "simulated": 0, "failed": 0, "no_email": 0, "duplicate": 0}
    limit_left = DAILY_LIMIT - (sent_today(conn) if real_send else 0)

    for r in rows:
        if not r["email"] or not EMAIL_RE.match(r["email"]):
            stats["no_email"] += 1
            continue
        if already_contacted(conn, r["channel_id"], r["email"], real_send):
            stats["duplicate"] += 1
            continue
        if stats["sent"] + stats["simulated"] >= limit_left:
            print("Daily limit reached")
            break

        to_addr = TEST_RECIPIENT or r["email"]
        email = build_email(r, to_addr)

        if not real_send:
            log(conn, r["channel_id"], "email", r["email"], "simulated", to_addr)
            stats["simulated"] += 1
            print(f"  [DRY RUN] {r['name']} <{to_addr}> : {r['email_subject']}")
            continue

        try:
            smtp.send_message(email)
            log(conn, r["channel_id"], "email", r["email"], "sent", to_addr)
            stats["sent"] += 1
            print(f"  SENT {r['name']} -> {to_addr}")
            time.sleep(SECONDS_BETWEEN_EMAILS)
        except Exception as e:
            log(conn, r["channel_id"], "email", r["email"], "failed", to_addr, str(e)[:300])
            stats["failed"] += 1
            print(f"  FAIL {r['name']}: {e}")

    if smtp:
        smtp.quit()
    print("Email:", stats)
    conn.close()


def queue_instagram_dms():
    """Cold DMs can't be automated on Instagram, so they go to a manual queue."""
    init_db()
    conn = get_conn()
    rows = conn.execute("""
        SELECT i.channel_id, i.instagram FROM influencers i
        JOIN messages m ON i.channel_id = m.channel_id
        WHERE i.filter_status = 'PASS' AND i.instagram IS NOT NULL
          AND i.channel_id NOT IN (SELECT channel_id FROM outreach_log WHERE channel = 'instagram_dm')
    """).fetchall()
    for r in rows:
        log(conn, r["channel_id"], "instagram_dm", r["instagram"], "pending_manual")
    print(f"Instagram DMs queued for manual sending: {len(rows)}")
    conn.close()


def mark_dm_sent(channel_id):
    conn = get_conn()
    cur = conn.execute(
        "UPDATE outreach_log SET status = 'sent_manual' WHERE channel_id = ? AND channel = 'instagram_dm'",
        (channel_id,))
    conn.commit()
    print("Marked as sent" if cur.rowcount else "No queued DM for this channel")
    conn.close()


if __name__ == "__main__":
    # python sender.py                      dry run
    # python sender.py --send               real send via Gmail SMTP
    # python sender.py --dm-sent <id>       mark an Instagram DM as sent manually
    if "--dm-sent" in sys.argv:
        mark_dm_sent(sys.argv[-1])
    else:
        send_emails(real_send="--send" in sys.argv)
        queue_instagram_dms()
