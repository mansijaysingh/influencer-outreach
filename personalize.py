import json
import re
import sys
import time
from datetime import datetime

from dotenv import load_dotenv
from google import genai
from google.genai import types

from config import BRAND, GEMINI_MODEL, NICHE, SECONDS_BETWEEN_CALLS
from db import get_conn, init_db

load_dotenv()
client = genai.Client()

SYSTEM_PROMPT = """You write influencer outreach messages for a brand.
You get verified facts about ONE YouTube creator and the brand.

Write:
- email_subject: max 9 words, specific to this creator.
- email_body: 60-90 words. Greeting + body only (no signature).
  Mention at least ONE of their recent video titles or content themes by name,
  explain why their audience fits the product, state the collaboration angle clearly,
  end with a simple question.
- instagram_dm: 15-30 words, casual, mention one specific video/theme, no links.

Rules:
- Use ONLY the facts given. Never invent numbers, past collabs, audience details or first names.
- Address them by channel name (not a guessed first name).
- Do not mention their follower count or engagement numbers.
- No generic lines like "we'd love to collaborate" without a specific reason.
- Pitch ONLY the given collaboration_angle. Do not add other deal types or offers.
- No emojis or hashtags in the email, max one emoji in the DM.

Return JSON: {"email_subject": "...", "email_body": "...", "instagram_dm": "..."}"""


def clean(text):
    """Strip emojis, hashtags and stray symbols from names and titles."""
    text = re.sub(r"#\w+", "", text or "")
    text = re.sub(r"[^\w\s'&|:,.!?()-]", "", text)
    return re.sub(r"\s+", " ", text).strip(" |-")


def word_count(text):
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def collab_angle(inf):
    """Rule-based deal type from creator size and engagement."""
    subs, er = inf["subscribers"], inf["engagement_rate"]
    if subs < 15_000:
        return "Barter: free product in exchange for an honest review" if er >= 4 else "UGC: paid short videos for our ads"
    if subs < 50_000:
        return "Affiliate: personal discount code + 15% commission on sales" if er >= 5 else "Paid product placement in one video"
    return "Brand ambassador program (3 months)" if er >= 4 else "Sponsored integration in one upcoming video"


def validate(msg, titles, themes):
    """Checks the LLM output in code. Returns a list of problems."""
    if not isinstance(msg, dict):
        return ["response is not a JSON object"]
    errors = [f"missing {k}" for k in ("email_subject", "email_body", "instagram_dm") if not msg.get(k)]
    if errors:
        return errors

    ew, dw = word_count(msg["email_body"]), word_count(msg["instagram_dm"])
    if not 60 <= ew <= 90:
        errors.append(f"email_body has {ew} words, needs 60-90")
    if not 15 <= dw <= 30:
        errors.append(f"instagram_dm has {dw} words, needs 15-30")

    # anti-generic check: must reuse at least one word from the creator's own titles/themes
    text = (msg["email_body"] + " " + msg["instagram_dm"]).lower()
    source_words = set(re.findall(r"[a-z]{5,}", (" ".join(titles) + " " + themes).lower()))
    if source_words and not any(w in text for w in source_words):
        errors.append("does not mention any specific video or theme of this creator")
    return errors


def ask_gemini(prompt):
    """Gemini call with back-off for 503 / rate-limit errors."""
    for attempt in range(4):
        try:
            res = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.7,
                ),
            )
            return json.loads(res.text)
        except Exception as e:
            wait = 10 * (attempt + 1)
            print(f"    Gemini error ({e.__class__.__name__}), retry in {wait}s")
            time.sleep(wait)
    raise RuntimeError("Gemini failed after 4 attempts")


def generate_for(inf):
    titles = [clean(t) for t in json.loads(inf["recent_titles"] or "[]")[:3]]
    angle = collab_angle(inf)
    facts = {
        "creator": {
            "channel_name": clean(inf["name"]),
            "niche": NICHE,
            "content_themes": inf["content_themes"],
            "recent_video_titles": titles,
            "country": inf["country"] or "unknown",
        },
        "brand": {"name": BRAND["name"], "product": BRAND["product"]},
        "collaboration_angle": angle,
    }
    prompt = json.dumps(facts, indent=2, ensure_ascii=False)

    feedback = ""
    for attempt in range(1, 4):
        msg = ask_gemini(prompt + feedback)
        errors = validate(msg, titles, inf["content_themes"] or "")
        if not errors:
            return msg, angle, attempt
        feedback = "\n\nYour last answer was rejected: " + "; ".join(errors) + ". Fix it and return full JSON again."
        print(f"    attempt {attempt} rejected: {errors}")
        time.sleep(SECONDS_BETWEEN_CALLS)
    raise ValueError("; ".join(errors))


def personalize(limit=None):
    init_db()
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM influencers
        WHERE filter_status = 'PASS'
          AND channel_id NOT IN (SELECT channel_id FROM messages)
    """).fetchall()
    if limit:
        rows = rows[:limit]
    print(f"Generating messages for {len(rows)} influencers...")

    done = 0
    for inf in rows:
        try:
            msg, angle, attempts = generate_for(inf)
            conn.execute(
                "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (inf["channel_id"], angle, msg["email_subject"], msg["email_body"], word_count(msg["email_body"]),
                 msg["instagram_dm"], word_count(msg["instagram_dm"]), attempts, datetime.now().isoformat()),
            )
            conn.commit()
            done += 1
            print(f"  OK   {inf['name']} ({attempts} attempt)")
        except Exception as e:
            print(f"  FAIL {inf['name']}: {e}")
        time.sleep(SECONDS_BETWEEN_CALLS)

    print(f"\nGenerated: {done}/{len(rows)}")
    conn.close()


if __name__ == "__main__":
    # usage: python personalize.py [limit]
    personalize(int(sys.argv[1]) if len(sys.argv) > 1 else None)
