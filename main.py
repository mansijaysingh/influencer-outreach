"""Runs the full pipeline.

python main.py                     discover > enrich > filter > personalize > send (dry run) > export
python main.py --send              same, but sends real emails via Gmail SMTP
python main.py --skip-discovery    skip new searches (saves YouTube quota)
"""
import sys

from discovery import discover
from enrichment import enrich
from export import export
from filtering import run_filters
from personalize import personalize
from sender import queue_instagram_dms, send_emails


def main():
    args = sys.argv[1:]
    steps = [
        ("1. Discovery", None if "--skip-discovery" in args else discover),
        ("2. Enrichment", enrich),
        ("3. Filtering", run_filters),
        ("4. AI Personalization", personalize),
        ("5. Sending", lambda: send_emails(real_send="--send" in args)),
        ("   Instagram DM queue", queue_instagram_dms),
        ("6. Export CSVs", export),
    ]
    for name, fn in steps:
        print(f"\n===== {name} =====")
        if fn is None:
            print("skipped")
            continue
        fn()
    print("\nPipeline complete. Check the output/ folder.")


if __name__ == "__main__":
    main()