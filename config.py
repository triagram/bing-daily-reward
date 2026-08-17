import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).parent.resolve()
USER_DATA_DIR = BASE_DIR / "browser_session"

# Target URLs
REWARDS_URL = "https://rewards.bing.com/"
REWARDS_EARN_URL = "https://rewards.bing.com/earn"
BING_SEARCH_URL = "https://www.bing.com"

# Task Settings - Anti-bot & Points Registration Intervals
# The measured allowance on this UK account is 20 searches at 3 points (2026-08-16;
# searches 21-23 paid nothing). Differs by market — re-measure with
# experiments/q6_allowance.py elsewhere.
DAILY_SEARCH_ALLOWANCE = 20
POINTS_PER_SEARCH = 3          # measured alongside the allowance

# How many to actually run: deliberately short of the allowance, and different every
# day. See daily_search_count() in utils/humanizer.py for why.
# Searches are the lowest-yield action on the account at 3 points each, against
# 5-15 for an Explore offer and 10-30 for a daily-set card. So when trading volume
# for a lower profile, this is the number to cut — not the other tasks.
DAILY_SEARCH_MIN = 8
DAILY_SEARCH_MAX = 12

# Superseded by search_gap() in utils/humanizer.py, which draws from a heavy-tailed
# mixture instead of a flat window. Kept only for the older task modules.
MIN_DELAY_BETWEEN_SEARCHES = 6.0
MAX_DELAY_BETWEEN_SEARCHES = 9.0

# Most Explore offers a run will do. Observed outstanding counts have been 1-6, so
# this normally binds on nothing and every offer gets done — it exists only to stop a
# day where a backlog has piled up from becoming an unusually long burst of activity.
# Each offer is worth 5-15 points, several times a search, so trimming here is the
# expensive place to economise; prefer cutting searches (see DAILY_SEARCH_MIN/MAX).
EXPLORE_MAX_PER_RUN = 6

# Headless mode: Set to False for visual browser, True for background
HEADLESS = False

# Search Keywords Source Bank (diverse topics to ensure point registration)
FALLBACK_KEYWORDS = [
    "latest technology news",
    "best travel destinations 2026",
    "healthy breakfast ideas",
    "space exploration milestones",
    "climate change solutions",
    "artificial intelligence trends",
    "electric vehicles comparison",
    "popular movie reviews",
    "simple home workout routine",
    "historical events today",
    "gardening tips for beginners",
    "easy pasta recipes",
    "book recommendations 2026",
    "national parks travel guide",
    "cybersecurity best practices",
    "renewable energy innovations",
    "mindfulness meditation benefits",
    "financial planning tips",
    "astrophotography guide",
    "smart home gadgets"
]
