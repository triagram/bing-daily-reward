import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).parent.resolve()
USER_DATA_DIR = BASE_DIR / "browser_session"

# Target URLs
REWARDS_URL = "https://rewards.bing.com/"
REWARDS_EARN_URL = "https://rewards.bing.com/earn"

# The measured allowance on this account is 20 searches at 3 points (2026-08-16;
# searches 21-23 paid nothing). Differs by market. The run reads the day's real figure
# from the points breakdown; this constant documents the ceiling and anchors the tests.
DAILY_SEARCH_ALLOWANCE = 20
POINTS_PER_SEARCH = 3          # measured alongside the allowance

# How many to actually run: deliberately short of the allowance, and different every
# day. See daily_search_count() in utils/humanizer.py for why.
# Searches are the lowest-yield action on the account at 3 points each, against
# 5-15 for a Keep-earning offer and 10-30 for a daily-set card. So when trading volume
# for a lower profile, this is the number to cut — not the other tasks.
DAILY_SEARCH_MIN = 8
DAILY_SEARCH_MAX = 12

# Most Keep-earning offers a run will do. Observed outstanding counts have been 1-6, so
# this normally binds on nothing and every offer gets done — it exists only to stop a
# day where a backlog has piled up from becoming an unusually long burst of activity.
# Each offer is worth 5-15 points, several times a search, so trimming here is the
# expensive place to economise; prefer cutting searches (see DAILY_SEARCH_MIN/MAX).
KEEP_EARNING_MAX_PER_RUN = 6

# Explore on Bing inside the daily run. Off until the test period that followed the
# observation window closes (2026-09-23): until then the tiles are worked by
# explore_on_bing.py after the daily run, so that an unlearned tile cannot flag a day
# whose measurement is already recorded. When on, the tiles' own typed searches are
# reserved out of the day's search allowance — four tiles, four searches — so that the
# drawn count plus the tiles cannot land on the quota.
RUN_EXPLORE_ON_BING = True
EXPLORE_ON_BING_TILES_PER_DAY = 4

# Headless mode: Set to False for visual browser, True for background
HEADLESS = False
