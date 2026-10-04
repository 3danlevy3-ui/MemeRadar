"""Rolling mention state + burst detection. Pure functions: easy to test and replay."""
import math
import time
from collections import defaultdict

from . import config as C
from .tickers import extract


def hour_key(ts):
    return time.strftime("%Y%m%d%H", time.gmtime(int(ts)))


def new_state():
    return {"hours": {}, "seen": {}, "alerts": {}, "last_run": 0, "backfilled": False}


def ingest(state, items, universe):
    """Annotate fetched comments/posts with the tickers they mention and add the ones not
    counted before (id-deduped across runs) to the hourly buckets. Returns all unique items."""
    out, batch = [], set()
    for it in items:
        iid = it.get("id")
        if not iid or iid in batch:
            continue
        batch.add(iid)
        ts = int(it["created_utc"])
        text = " ".join(filter(None, [it.get("title"), it.get("selftext"), it.get("body")]))
        tks = extract(text, universe)
        if iid not in state["seen"]:
            state["seen"][iid] = ts
            h = state["hours"].setdefault(hour_key(ts), {"_c": 0, "T": {}})
            h["_c"] += 1
            for t in tks:
                h["T"][t] = h["T"].get(t, 0) + 1
        out.append({"id": iid, "t": ts, "a": it.get("author") or "", "tk": sorted(tks), "text": text[:600]})
    return out


def prune(state, now):
    cut_h = hour_key(now - C.STATE_KEEP_DAYS * 86400)
    state["hours"] = {k: v for k, v in state["hours"].items() if k >= cut_h}
    state["seen"] = {k: v for k, v in state["seen"].items() if v >= now - 3 * 3600}


def window_stats(items, now, minutes=60):
    """Mentions, unique authors and sample texts per ticker in the last `minutes`."""
    lo = now - minutes * 60
    m, a, tx = defaultdict(int), defaultdict(set), defaultdict(list)
    total = 0
    for it in items:
        if it["t"] < lo:
            continue
        total += 1
        for t in it["tk"]:
            m[t] += 1
            a[t].add(it["a"])
            if len(tx[t]) < 60:
                tx[t].append(it["text"])
    return m, {k: len(v) for k, v in a.items()}, tx, total


def baseline(state, ticker, now, days=14, exclude_hours=6):
    """Mean hourly mentions and mention share over observed hours in [now-days, now-exclude]."""
    lo, hi = hour_key(now - days * 86400), hour_key(now - exclude_hours * 3600)
    hours = [v for k, v in state["hours"].items() if lo <= k < hi and v["_c"] > 0]
    n = len(hours)
    if not n:
        return 0.0, 0.0, 0
    tk = sum(h["T"].get(ticker, 0) for h in hours)
    tot = sum(h["_c"] for h in hours)
    return tk / n, (tk / tot if tot else 0.0), n


def recent_sum(state, ticker, now, hours=6):
    keys = {hour_key(now - i * 3600) for i in range(hours)}
    return sum(state["hours"].get(k, {"T": {}})["T"].get(ticker, 0) for k in keys)


def evaluate(state, m60, a60, total60, now):
    """Score every ticker seen in the last hour; return candidates sorted by score."""
    out = []
    for t, cnt in m60.items():
        if cnt < max(2, C.MIN_MENTIONS_1H // 2):
            continue
        base_h, base_share, hist = baseline(state, t, now)
        floor = C.MIN_BASELINE if hist >= C.MIN_HISTORY_HOURS else 1.0  # be stricter while warming up
        burst = cnt / max(base_h, floor)
        share = cnt / total60 if total60 else 0.0
        share_burst = share / max(base_share, 1e-4) if base_share else share / 1e-4 if share else 0.0
        authors = a60.get(t, 0)
        fired = (cnt >= C.MIN_MENTIONS_1H and authors >= C.MIN_AUTHORS_1H and burst >= C.BURST_MULT
                 and share_burst >= C.SHARE_MULT and t not in C.MEGA)
        score = (45 * min(1.0, math.log(max(burst, 1)) / math.log(50))
                 + 25 * min(1.0, authors / 40)
                 + 20 * min(1.0, math.log(max(share_burst, 1)) / math.log(50)))
        out.append({"ticker": t, "mentions_1h": cnt, "authors_1h": authors, "baseline_h": round(base_h, 2),
                    "burst": round(burst, 1), "share_burst": round(share_burst, 1), "history_h": hist,
                    "score": round(score), "fired": fired})
    return sorted(out, key=lambda r: (-r["fired"], -r["score"]))


def check_exits(state, now, price_fn):
    """Follow-up on open alerts: mentions fading, trailing stop, or time limit."""
    exits = []
    for t, al in list(state["alerts"].items()):
        if al.get("closed"):
            continue
        m6 = recent_sum(state, t, now, 6)
        al["peak_m6"] = max(al.get("peak_m6", 0), m6)
        px = price_fn(t)
        reason = None
        if px.get("ok"):
            al["peak_price"] = max(al.get("peak_price", 0) or 0, px["price"])
            al["last_price"] = px["price"]
            if al["peak_price"] and px["price"] <= al["peak_price"] * (1 - C.EXIT_TRAIL_STOP):
                reason = f"price {C.EXIT_TRAIL_STOP:.0%} below the peak since the alert"
        age_h = (now - al["time"]) / 3600
        if not reason and al["peak_m6"] >= 10 and m6 < al["peak_m6"] * C.EXIT_MENTION_DECAY and age_h > 6:
            reason = f"chatter faded to {m6} mentions/6h (peak {al['peak_m6']})"
        if not reason and age_h > C.EXIT_MAX_HOURS:
            reason = f"time limit {C.EXIT_MAX_HOURS}h"
        if reason:
            al["closed"] = now
            ret = (al["last_price"] / al["entry_price"] - 1) if al.get("entry_price") and al.get("last_price") else None
            exits.append({"ticker": t, "reason": reason, "ret": ret, "alert": al})
    # forget closed alerts after a week
    state["alerts"] = {t: a for t, a in state["alerts"].items() if not a.get("closed") or now - a["closed"] < 7 * 86400}
    return exits


def should_alert(state, c, now):
    prev = state["alerts"].get(c["ticker"])
    if not prev or prev.get("closed"):
        return not prev or now - prev.get("closed", 0) > C.ALERT_COOLDOWN_H * 3600
    # already open: only re-alert if it escalated from EARLY->MOMENTUM or score jumped a lot
    return (now - prev["time"] > C.ALERT_COOLDOWN_H * 3600) or (c["score"] >= prev["score"] + 20)


# ---------------------------------------------------------------- multi-source fusion
def st_update(state, ticker, st, bursting):
    """Keep an EMA of each ticker's normal Stocktwits message rate (only updated when not bursting)."""
    rates = state.setdefault("st_rate", {})
    prev = rates.get(ticker)
    if st and not bursting:
        rates[ticker] = st["rate_h"] if prev is None else round(0.8 * prev + 0.2 * st["rate_h"], 3)
    return prev


def st_signal(st, ema, new_trending):
    if not st:
        return False, None
    burst = st["n_1h"] / max(ema if ema is not None else 0.5, 0.5)
    fired = st["n_1h"] >= C.ST_MIN_MSGS_1H and (burst >= C.ST_BURST_MULT or (ema is None and new_trending))
    return fired, round(burst, 1)


def x_signal(xc):
    if not xc:
        return False, None
    burst = xc["x_1h"] / max(xc["x_base_h"], 1.0)
    return (xc["x_1h"] >= C.X_MIN_1H and burst >= C.X_BURST_MULT), round(burst, 1)


def fuse(c):
    """Combine sources into one 0-100 score. c carries per-source fields; returns c with score/tier/sources."""
    src = []
    s = 0.0
    if c.get("reddit_fired"):
        src.append("Reddit")
        s += 18 + 17 * min(1.0, math.log(max(c.get("burst", 1), 1)) / math.log(50))
    if c.get("st_fired"):
        src.append("Stocktwits")
        s += 12 + 10 * min(1.0, math.log(max(c.get("st_burst") or 1, 1)) / math.log(20))
    if c.get("x_fired"):
        src.append("X")
        s += 12 + 10 * min(1.0, math.log(max(c.get("x_burst") or 1, 1)) / math.log(50))
    if c.get("influencer"):
        src.append("X-influencer")
        s += 30
    if len(src) >= 2:
        s += 10                                           # independent confirmation
    si = c.get("si") or {}
    if si.get("dtc") and si["dtc"] >= C.DTC_HIGH:
        s += 10 if si["dtc"] < 7 else 15                   # squeeze fuel + (in backtest) fewer -15% crashes
    opt = c.get("options") or {}
    if (opt.get("cp_ratio") or 0) >= 3 and (opt.get("call_vol_oi") or 0) >= 0.5:
        s += 10                                            # unusual call buying
    early = c.get("move_24h") is None or c["move_24h"] < C.EARLY_MAX_MOVE * 100
    c["tier"] = "EARLY" if early else "MOMENTUM"
    if early:
        s += 8
    c["sources"] = src
    c["score"] = int(min(100, round(s)))
    return c


# ---------------------------------------------------------------- quality flags
def _norm(text):
    import re
    return re.sub(r"[^a-z0-9$ ]", "", text.lower())[:160].strip()


def quality(items, now, minutes=60):
    """Per ticker: share of copy-pasted texts and share of mentions from the single busiest author."""
    lo = now - minutes * 60
    per = defaultdict(list)
    for it in items:
        if it["t"] >= lo:
            for t in it["tk"]:
                per[t].append((it["a"], _norm(it["text"])))
    out = {}
    for t, rows in per.items():
        n = len(rows)
        if n < 4:
            continue
        texts = [x for _, x in rows if len(x) >= 12]
        dup = 1 - len(set(texts)) / len(texts) if texts else 0.0
        counts = defaultdict(int)
        for a, _ in rows:
            counts[a] += 1
        out[t] = {"dup": round(dup, 2), "top_author": round(max(counts.values()) / n, 2)}
    return out


def apply_flags(c, q=None, earnings=None, trends=None):
    """Adjust score with quality/context flags; returns c with c['flags'] (Hebrew labels)."""
    flags, adj = [], 0
    if c.get("reddit_fired") and c.get("baseline_h") is not None and c["baseline_h"] < C.FROM_ZERO_BASE:
        flags.append("🆕 מאפס: כמעט לא דיברו עליה לפני")
        adj += 8
    if q and (q["dup"] >= C.SPAM_DUP_RATIO or q["top_author"] >= C.SPAM_TOP_AUTHOR):
        flags.append(f"⚠️ חשד לספאם: {int(q['dup'] * 100)}% הודעות משוכפלות, כותב אחד = {int(q['top_author'] * 100)}%")
        adj -= 15
    if earnings:
        flags.append("📅 דוחות כספיים סביב היום: הרעש צפוי")
        adj -= 10
    if trends and trends.get("ratio") is not None and trends["ratio"] >= C.TRENDS_BOOST_RATIO:
        adj += 6
    c["flags"] = flags
    c["score"] = int(max(0, min(100, c.get("score", 0) + adj)))
    return c
