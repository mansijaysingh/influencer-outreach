import os

from dotenv import load_dotenv

load_dotenv()

NICHE = "Fitness"

# ---- Discovery ----
SEARCH_QUERIES = [
    "my fitness journey week",
    "beginner home workout vlog",
    "calisthenics progress update",
    "gym diet what I eat in a day",
    "postpartum workout routine",
    "workout for women over 40",
    "desi diet fat loss",
    "home workout hindi",
    "kettlebell workout routine",
    "resistance band workout",
    "marathon training vlog",
    "powerlifting meet prep",
]
TARGET_CANDIDATES = 300
PAGES_PER_QUERY = 2
RECENT_DAYS = 120

DB_PATH = "outreach.db"

# ---- Enrichment ----
RECENT_VIDEOS = 10
NICHE_KEYWORDS = [
    "workout", "fitness", "gym", "exercise", "training", "strength", "muscle",
    "fat loss", "weight loss", "calisthenics", "yoga", "cardio", "hiit",
    "mobility", "stretch", "protein", "meal prep", "running", "bodybuilding",
    "abs", "pilates", "squat", "pushup", "push up",
]

# ---- Filtering ----
MIN_SUBSCRIBERS = 5_000
MAX_SUBSCRIBERS = 100_000
MIN_ENGAGEMENT = 2.0          # percent
MAX_DAYS_SINCE_UPLOAD = 60
MIN_RELEVANCE = 0.3           # share of recent titles that are fitness-related
ALLOWED_COUNTRIES = []        # e.g. ["IN", "US"]; empty = any country
BLOCKLIST = ["casino", "betting", "gambling", "onlyfans", "steroid", "sarms"]

# ---- AI personalization ----
GEMINI_MODEL = "gemini-3.5-flash-lite"
SECONDS_BETWEEN_CALLS = 5     # stays under the free-tier rate limit

BRAND = {
    "name": "FitFuel",        # fictional demo brand
    "product": "plant-based protein bars",
    "sender_name": "Aman",
    "sender_title": "Partnerships Intern",
}

# ---- Sending ----
TEST_RECIPIENT = os.getenv("TEST_RECIPIENT", "")   # set in .env; redirects every email there
DAILY_LIMIT = 30
SECONDS_BETWEEN_EMAILS = 3
