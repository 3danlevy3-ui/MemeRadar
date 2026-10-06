"""Signals from the GME / AMC / BB deep dive (Oct 2026, site/meme_dna.html).

Each rule adds a Hebrew flag (so the journal can later tell whether it helps) and a small score
bonus. None of them can raise an alert on its own: they only strengthen buzz the scanner already saw.

  wave        a meme just spiked; stocks co-mentioned with it ("the next GME") get attention
  hype_shift  the stock's posts switch from analysis to hype (rockets, moon, diamond hands)
  engagement  posts about the stock get far more upvotes than the forum's average post
  newcomers   most people writing about it never wrote about it before
  slow_burn   share of the conversation grew week after week for a month (GME 2020 style)
"""
import hashlib
import re
import time
from collections import defaultdict

from . import config as C

HYPE = re.compile(r"\bmoon|tendies|rocket|lfg|\bapes?\b|hodl|diamond hands?|\bhold(ing)?\b|"
                  r"\U0001F680|\U0001F48E|\U0001F64C|\U0001F98D|\U0001F315", re.I)
DD = re.compile(r"\bdd\b|due diligence|thesis|valuation|undervalued|revenue|balance sheet|"
                r"catalyst|earnings|guidance|book value|cash flow", re.I)
NEXT = r"next\s+\$?{t}\b|another\s+\$?{t}\b|\$?{t}\s*2\.0|like\s+\$?{t}\b|the\s+new\s+\$?{t}\b"
DAY = 86400


def _day(ts):
    return time.strftime("%Y%m%d", time.gmtime(int(ts)))


def _h(author):
    return hashlib.md5((author or "").encode()).hexdigest()[:6]


# ------------------------------------------------------------------ wave
def wave_leaders(state, journal_entries, now):
    """Stocks that spiked in the last WAVE_DAYS: a phone alert, or a +20% day on 3x volume."""
    leaders = set()
    for t, al in (state.get("alerts") or {}).items():
        if now - al.get("time", 0) < C.WAVE_DAYS * DAY:
            leaders.add(t)
    for e in journal_entries:
        if now - e["t"] < C.WAVE_DAYS * DAY and (e.get("move_24h") or 0) >= 20 and (e.get("rel_volume") or 0) >= 3:
            leaders.add(e["ticker"])
    return leaders


def wave_followers(items, leaders, now, minutes=60):
    """{ticker: (leader, n_posts)} for stocks mentioned alongside a leader, or as 'the next <leader>'."""
    lo = now - minutes * 60
    co = defaultdict(lambda: defaultdict(int))
    for it in items:
        if it["t"] < lo or not it["tk"]:
            continue
        hit = [ld for ld in leaders if ld in it["tk"]]
        if not hit:
            continue
        txt = it["text"]
        for ld in hit:
            nxt = re.search(NEXT.format(t=re.escape(ld)), txt, re.I)
            for t in it["tk"]:
                if t != ld and t not in leaders and t not in C.MEGA:
                    co[t][ld] += 2 if nxt else 1
    out = {}
    for t, d in co.items():
        ld, n = max(d.items(), key=lambda kv: kv[1])
        if n >= C.WAVE_MIN_CO:
            out[t] = (ld, n)
    return out


# ------------------------------------------------------------------ hype shift
def hype_share(texts):
    """(hype share, analysis share) of a stock's posts/comments."""
    texts = [x for x in texts or [] if x]
    if not texts:
        return 0.0, 0.0
    return (sum(1 for x in texts if HYPE.search(x)) / len(texts),
            sum(1 for x in texts if DD.search(x)) / len(texts))


def hype_shift(state, ticker, texts):
    """Compare this hour's hype share with the stock's own running average; then update the average."""
    hs, dd = hype_share(texts)
    book = state.setdefault("hype", {})
    ema, n = (book.get(ticker) or [None, 0])[:2]
    res = None
    if len(texts) >= C.HYPE_MIN_TEXTS and ema is not None and n >= C.HYPE_MIN_OBS:
        ratio = hs / max(ema, 0.05)
        res = {"share": round(hs, 2), "base": round(ema, 2), "ratio": round(ratio, 1), "dd": round(dd, 2),
               "fired": hs >= C.HYPE_MIN_SHARE and ratio >= C.HYPE_SHIFT_MULT}
    if len(texts) >= 3:
        book[ticker] = [round(hs if ema is None else ema + 0.2 * (hs - ema), 3), n + 1, int(time.time())]
    return res


# ------------------------------------------------------------------ engagement
def engagement(items, ticker, now, minutes=60):
    """Average upvotes of the stock's posts vs. every post in the same window (same age, fair comparison)."""
    lo = now - minutes * 60
    allv = [it.get("s") for it in items if it["t"] >= lo and it.get("s") is not None]
    mine = [it.get("s") for it in items if it["t"] >= lo and ticker in it["tk"] and it.get("s") is not None]
    if len(mine) < C.ENG_MIN_ITEMS or not allv:
        return None
    avg_all = max(sum(allv) / len(allv), 1.0)
    ratio = (sum(mine) / len(mine)) / avg_all
    return {"ratio": round(ratio, 1), "n": len(mine), "fired": ratio >= C.ENG_MULT}


# ------------------------------------------------------------------ newcomers
def newcomers(state, items, ticker, now, minutes=60):
    """Share of this hour's writers about the stock who had not written about it in the last 14 days.
    Kept compact: 6-character hashes of usernames, per stock, capped."""
    lo = now - minutes * 60
    authors = {it["a"] for it in items if it["t"] >= lo and ticker in it["tk"] and it["a"] not in ("", "[deleted]", "AutoModerator")}
    book = state.setdefault("authors", {})
    rec = book.get(ticker) or {"since": now, "a": {}}
    known = rec["a"]
    res = None
    if len(authors) >= C.NEW_MIN_AUTHORS and now - rec["since"] >= C.NEW_WARMUP_DAYS * DAY:
        fresh = [a for a in authors if _h(a) not in known]
        share = len(fresh) / len(authors)
        res = {"share": round(share, 2), "n": len(authors), "fired": share >= C.NEW_SHARE}
    today = int(now // DAY)
    for a in authors:
        known[_h(a)] = today
    if len(known) > C.NEW_CAP:
        for k, _ in sorted(known.items(), key=lambda kv: kv[1])[:len(known) - C.NEW_CAP]:
            del known[k]
    rec["a"], rec["last"] = known, now
    book[ticker] = rec
    return res


def prune_authors(state, now):
    book = state.get("authors") or {}
    cut = int(now // DAY) - 14
    for t in list(book):
        rec = book[t]
        rec["a"] = {k: d for k, d in rec["a"].items() if d >= cut}
        if not rec["a"] or now - rec.get("last", 0) > 14 * DAY:
            del book[t]


# ------------------------------------------------------------------ slow burn
def roll_days(state, now):
    """Daily mention counts per stock (kept 42 days; hourly buckets only last 15)."""
    days = state.setdefault("days", {})
    fresh = defaultdict(lambda: {"_c": 0, "T": defaultdict(int)})
    for k, h in state.get("hours", {}).items():
        d = k[:8]
        fresh[d]["_c"] += h.get("_c", 0)
        for t, n in h.get("T", {}).items():
            fresh[d]["T"][t] += n
    today = _day(now)
    for d, v in fresh.items():
        if d == today:
            continue                     # only complete days
        days[d] = {"_c": v["_c"], "T": {t: n for t, n in v["T"].items() if n >= 3}}
    cut = _day(now - 42 * DAY)
    for d in [d for d in days if d < cut]:
        del days[d]


def slow_burn(state, now, weeks=None):
    """Stocks whose share of the conversation rose every week for `weeks` weeks (GME, Jul 2020 to Jan 2021)."""
    weeks = weeks or C.SLOW_WEEKS
    days = state.get("days") or {}
    blocks = []
    for w in range(weeks, 0, -1):
        ds = [_day(now - (7 * w - i) * DAY) for i in range(7)]
        tot = sum(days.get(d, {}).get("_c", 0) for d in ds)
        if tot == 0 or sum(1 for d in ds if d in days) < 5:
            return []                    # not enough history yet
        cnt = defaultdict(int)
        for d in ds:
            for t, n in days.get(d, {}).get("T", {}).items():
                cnt[t] += n
        blocks.append((tot, cnt))
    out = []
    for t in blocks[-1][1]:
        if t in C.MEGA:
            continue
        shares = [b[1].get(t, 0) / b[0] for b in blocks]
        last_n = blocks[-1][1].get(t, 0)
        rising = all(shares[i + 1] >= shares[i] * C.SLOW_STEP and shares[i + 1] > 0 for i in range(len(shares) - 1))
        if rising and last_n >= C.SLOW_MIN_MENTIONS and shares[-1] >= C.SLOW_MIN_SHARE:
            out.append({"ticker": t, "shares": [round(s * 100, 2) for s in shares], "mentions": last_n,
                        "growth": round(shares[-1] / max(shares[0], 1e-6), 1)})
    return sorted(out, key=lambda x: -x["growth"])[:8]


# ------------------------------------------------------------------ apply to a candidate
def apply(c, state, items, texts, now, followers):
    """Add research flags and bonuses to an alert candidate. Returns the list of rule names that fired."""
    t = c["ticker"]
    fired, adj = [], 0
    flags = c.setdefault("flags", [])
    if t in followers:
        ld, n = followers[t]
        c["wave"] = ld
        flags.append(f"🌊 רוכבת על הגל של ${ld}: מוזכרת איתה ב-{n} פוסטים")
        fired.append("wave")
        adj += C.WAVE_BONUS
    hsft = hype_shift(state, t, texts)
    if hsft:
        c["hype"] = hsft
        if hsft["fired"]:
            flags.append(f"🔥 מעבר להייפ: {int(hsft['share'] * 100)}% מההודעות עם 🚀/moon/💎, פי {hsft['ratio']:g} מהרגיל")
            fired.append("hype_shift")
            adj += C.HYPE_BONUS
    eng = engagement(items, t, now)
    if eng:
        c["engagement"] = eng
        if eng["fired"]:
            flags.append(f"👍 מעורבות גבוהה: הפוסטים עליה מקבלים פי {eng['ratio']:g} לייקים מהממוצע")
            fired.append("engagement")
            adj += C.ENG_BONUS
    nc = newcomers(state, items, t, now)
    if nc:
        c["newcomers"] = nc
        if nc["fired"]:
            flags.append(f"👥 קהל חדש: {int(nc['share'] * 100)}% מהכותבים לא כתבו עליה קודם")
            fired.append("newcomers")
            adj += C.NEW_BONUS
    if t in {x["ticker"] for x in state.get("slow_burn") or []}:
        flags.append("🐢 בעירה איטית: השיח עליה עולה כבר כמה שבועות ברציפות")
        fired.append("slow_burn")
        adj += C.SLOW_BONUS
    c["score"] = int(max(0, min(100, c.get("score", 0) + adj)))
    c["research"] = fired
    return fired
