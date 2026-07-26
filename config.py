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
DAILY_SEARCH_COUNT = 20  # 20 searches daily (3 pts each = 60 pts)
MIN_DELAY_BETWEEN_SEARCHES = 6.0  # seconds (Required for Bing points counter cooldown)
MAX_DELAY_BETWEEN_SEARCHES = 9.0  # seconds

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
