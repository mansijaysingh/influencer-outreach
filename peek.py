from db import get_conn

conn = get_conn()
rows = conn.execute("""
    SELECT i.name, i.email, i.recent_titles, m.collab_angle,
           m.email_subject, m.email_body, m.email_words,
           m.instagram_dm, m.dm_words
    FROM messages m JOIN influencers i ON i.channel_id = m.channel_id
    LIMIT 3
""").fetchall()

for r in rows:
    print("=" * 70)
    print("Creator   :", r["name"], "|", r["email"])
    print("Titles    :", r["recent_titles"][:150])
    print("Angle     :", r["collab_angle"])
    print("Subject   :", r["email_subject"])
    print(f"Email ({r['email_words']} words):\n{r['email_body']}")
    print(f"\nDM ({r['dm_words']} words): {r['instagram_dm']}")
conn.close()