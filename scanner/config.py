"""MemeRadar configuration. Every value can be overridden with an env var of the same name."""
import os


def _env(name, default, cast=str):
    v = os.environ.get(name)
    return cast(v) if v not in (None, "") else default


# --- sources -------------------------------------------------------------
SUBREDDITS = _env("SUBREDDITS", "wallstreetbets,stocks,shortsqueeze,pennystocks,Superstonk,WallStreetbetsELITE,smallstreetbets").split(",")
ARCTIC = "https://arctic-shift.photon-reddit.com"
USER_AGENT = _env("USER_AGENT", "MemeRadar/1.0 (personal research scanner)")
LOOKBACK_MIN = _env("LOOKBACK_MIN", 60, int)          # window scanned on every run
MAX_PAGES_PER_SUB = _env("MAX_PAGES_PER_SUB", 80, int)  # 100 items per page
BACKFILL_HOURS = _env("BACKFILL_HOURS", 72, int)       # baseline history to build up
BACKFILL_BUDGET_S = _env("BACKFILL_BUDGET_S", 360, int)  # max seconds per run spent on backfill

# --- signal thresholds (calibrated in analysis/backtest.py) ----------------
MIN_MENTIONS_1H = _env("MIN_MENTIONS_1H", 8, int)
MIN_AUTHORS_1H = _env("MIN_AUTHORS_1H", 5, int)
BURST_MULT = _env("BURST_MULT", 5.0, float)      # last hour vs 14-day hourly baseline
SHARE_MULT = _env("SHARE_MULT", 4.0, float)      # share-of-voice vs baseline share
MIN_BASELINE = 0.3                               # floor for hourly baseline (unknown / new tickers)
MIN_HISTORY_HOURS = _env("MIN_HISTORY_HOURS", 24, int)
EARLY_MAX_MOVE = _env("EARLY_MAX_MOVE", 0.10, float)  # price move in last 24h to still call it "early"
ALERT_COOLDOWN_H = _env("ALERT_COOLDOWN_H", 12, int)
TOP_CANDIDATES = _env("TOP_CANDIDATES", 12, int)

# --- exit / follow-up ------------------------------------------------------
EXIT_MENTION_DECAY = _env("EXIT_MENTION_DECAY", 0.35, float)  # 6h mentions < 35% of peak
EXIT_TRAIL_STOP = _env("EXIT_TRAIL_STOP", 0.15, float)        # price 15% below peak since alert
EXIT_MAX_HOURS = _env("EXIT_MAX_HOURS", 72, int)

# --- notifications / LLM -------------------------------------------------
TELEGRAM_TOKEN = _env("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-sonnet-4-5")

STATE_PATH = _env("STATE_PATH", "state/state.json")
TICKERS_PATH = _env("TICKERS_PATH", "state/tickers.json")
STATE_KEEP_DAYS = 15

# Words that are valid tickers but are almost always just English / slang on WSB.
STOPWORDS = set("""
A I AM AN AS AT BE BY DO GO HE IF IN IS IT ME MY NO OF OK ON OR SO TO UP US WE
ALL AND ANY ARE BIG CAN CAR CEO CFO COO CTO DD DIP EOD EOW EPS ETF EV FDA FED FOR FUN GDP
HAS HOLD HUGE IPO IMO IRS IV ITM ATM OTM JUST KEY LOL LOVE MAN MOON NEW NOW NYSE ONE OPEN OUT
PM PT PUT PUTS CALL CALLS REAL RH RUN SEC SELL BUY TA TD TWO USA USD VERY WELL WSB YOLO FOMO
ATH ATL AI API APP BRO CASH CPI DOW EDIT EU UK FUD GAIN GOOD BEST HOPE LIFE LMAO MOM NICE
PLAY POST PUMP DUMP RIP SAFE SAVE TLDR WHY WOW YES YOY QOQ OTC ROI ETA FYI GG HODL BULL BEAR
RED GREEN LONG SHORT FREE NEXT OG ANY TOP LOW HIGH RATE TAX TV UI UX VC VR IQ CEOS ARK SUB
NFA IRA LLC INC CORP GOV POTUS SPAC FTX FAQ ICE CAT DOG EAT FAST GOLD HEAR LEAP LEAPS
""".split())
# Always-on chatter / indices; still tracked, but never called "early meme" signals.
MEGA = set("SPY QQQ IWM DIA VIX TSLA NVDA AAPL MSFT AMZN META GOOGL GOOG AMD".split())

# --- Stocktwits (free, no key) -------------------------------------------
USE_STOCKTWITS = _env("USE_STOCKTWITS", "1") == "1"
ST_MIN_MSGS_1H = _env("ST_MIN_MSGS_1H", 12, int)     # messages in the last hour (max 30 visible per call)
ST_BURST_MULT = _env("ST_BURST_MULT", 3.0, float)    # vs this ticker's usual hourly rate
ST_TOP_RANK = _env("ST_TOP_RANK", 15, int)           # counts as trending if rank <= this
MAX_MCAP_MUSD = _env("MAX_MCAP_MUSD", 20000, float)  # ignore trending large caps (> $20B)

# --- X / Twitter (paid: pay-per-use, ~$0.005 per request/post) -------------
X_BEARER_TOKEN = _env("X_BEARER_TOKEN", "")
X_DAILY_BUDGET = _env("X_DAILY_BUDGET", 1.0, float)  # USD per day, hard stop
X_MAX_PER_RUN = _env("X_MAX_PER_RUN", 3, int)        # post-count checks per run for candidates
X_WATCHLIST = [t for t in _env("X_WATCHLIST", "GME,AMC").split(",") if t]   # rotated, 1 per run
X_ACCOUNTS = [a for a in _env("X_ACCOUNTS", "TheRoaringKitty").split(",") if a]
X_MIN_1H = _env("X_MIN_1H", 30, int)
X_BURST_MULT = _env("X_BURST_MULT", 5.0, float)
X_COST = {"count": 0.005, "post": 0.005, "user": 0.010}

# --- market structure (free) ----------------------------------------------
USE_SHORT_INTEREST = _env("USE_SHORT_INTEREST", "1") == "1"   # FINRA, twice a month
USE_OPTIONS = _env("USE_OPTIONS", "1") == "1"                 # Nasdaq option chain
DTC_HIGH = _env("DTC_HIGH", 4.0, float)                       # days-to-cover that counts as squeeze fuel
HEALTH_HOUR_UTC = _env("HEALTH_HOUR_UTC", 5, int)             # daily status message (08:00 Israel)

# --- improvements v3 --------------------------------------------------------
JOURNAL_PATH = _env("JOURNAL_PATH", "state/journal.json")
DASHBOARD_PATH = _env("DASHBOARD_PATH", "docs/index.html")
USE_TRENDS = _env("USE_TRENDS", "1") == "1"          # Google Trends, best effort
USE_EARNINGS = _env("USE_EARNINGS", "1") == "1"      # Nasdaq earnings calendar
USE_CHARTS = _env("USE_CHARTS", "1") == "1"          # PNG chart with every alert
TRENDS_BOOST_RATIO = _env("TRENDS_BOOST_RATIO", 3.0, float)
SPAM_DUP_RATIO = _env("SPAM_DUP_RATIO", 0.4, float)   # share of copy-pasted texts
SPAM_TOP_AUTHOR = _env("SPAM_TOP_AUTHOR", 0.5, float)  # one author writing >= half the mentions
FROM_ZERO_BASE = _env("FROM_ZERO_BASE", 0.1, float)   # hourly baseline below this = "from zero"
# experiment rules shown with every alert and used for the paper-trading journal
TP_PCT = _env("TP_PCT", 0.30, float)
STOP_PCT = _env("STOP_PCT", 0.15, float)
HOLD_DAYS = _env("HOLD_DAYS", 3, int)
POSITION_PCT = _env("POSITION_PCT", 2.0, float)       # % of portfolio per idea
TRADE_COST = _env("TRADE_COST", 0.005, float)
WEEKLY_DOW = _env("WEEKLY_DOW", 5, int)               # 5 = Saturday (Python weekday)
WEEKLY_HOUR_UTC = _env("WEEKLY_HOUR_UTC", 6, int)     # 09:00 Israel
MAX_OUTCOME_FETCH = _env("MAX_OUTCOME_FETCH", 15, int)
PAGES_URL = _env("PAGES_URL", "")

# --- calmer alerts (v4) -------------------------------------------------------
PUSH_MIN_SCORE = _env("PUSH_MIN_SCORE", 70, int)      # instant push needs at least this score
PUSH_MAX_PER_DAY = _env("PUSH_MAX_PER_DAY", 3, int)   # hard cap on instant pushes per day
PUSH_COOLDOWN_H = _env("PUSH_COOLDOWN_H", 24, int)    # no second push for the same stock within this
SUSTAIN_MIN = _env("SUSTAIN_MIN", 10, int)            # buzz must still be there on the next scan (~15 min) before a push
DIGEST_HOUR_UTC = _env("DIGEST_HOUR_UTC", 12, int)    # daily list of stocks heating up (15:00 Israel, before US open)
BIG_CAP_BUSD = _env("BIG_CAP_BUSD", 10.0, float)      # market cap (billion $) treated as too big to meme
ST_MIN_OBS = _env("ST_MIN_OBS", 4, int)               # Stocktwits observations needed before trusting a burst

# --- extreme activity (v5) ----------------------------------------------------
EXTREME_MIN_MENTIONS = _env("EXTREME_MIN_MENTIONS", 25, int)   # mentions/hour pace
EXTREME_MIN_AUTHORS = _env("EXTREME_MIN_AUTHORS", 12, int)
EXTREME_BURST = _env("EXTREME_BURST", 20.0, float)             # x the stock's normal level
EXTREME_SCORE = _env("EXTREME_SCORE", 85, int)
EXTREME_PRICE_MOVE = _env("EXTREME_PRICE_MOVE", 20.0, float)   # % in 24h, with volume >= 4x
EXTREME_MAX_PER_DAY = _env("EXTREME_MAX_PER_DAY", 3, int)
EXTREME_COOLDOWN_H = _env("EXTREME_COOLDOWN_H", 6, int)

# --- mid-size moves track, paper only (v6) -----------------------------------
# Looser buzz rule, no phone message: every hit is logged and paper-traded with three
# target/stop rules so the data can show which one (if any) works. See analysis/midtrack.py.
MID_ENABLED = _env("MID_ENABLED", "1") == "1"
MID_MIN_PACE = _env("MID_MIN_PACE", 4, int)          # mentions/hour pace
MID_MIN_AUTHORS = _env("MID_MIN_AUTHORS", 2, int)
MID_BURST = _env("MID_BURST", 3.0, float)            # x the stock's normal level
MID_PER_RUN = _env("MID_PER_RUN", 6, int)            # price lookups per run for this track
MID_MAX_PER_DAY = _env("MID_MAX_PER_DAY", 30, int)
MID_COOLDOWN_H = _env("MID_COOLDOWN_H", 24, int)     # same stock logged at most once a day
MID_VOL_MULT = _env("MID_VOL_MULT", 3.0, float)      # the 'volume confirms' sub-group
MID_COST = _env("MID_COST", 0.01, float)             # round-trip spread + fees, small caps
MID_RULES = [(0.10, 0.07, 2), (0.15, 0.08, 3), (0.20, 0.10, 3)]   # (target, stop, days)
