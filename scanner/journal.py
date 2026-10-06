"""Paper-trading journal: every alert, what the stock did afterwards, and the weekly scorecard."""
import time

from . import config as C

DAY = 86400


def new_journal():
    return {"entries": [], "last_weekly": ""}


def record(j, c, now, chat_msg_id=None):
    """Store one alert. Returns its id (used by the Telegram feedback buttons)."""
    eid = f"{c['ticker']}-{now}"
    j["entries"].append({
        "id": eid, "t": now, "ticker": c["ticker"], "tier": c.get("tier"), "score": c.get("score"),
        "sources": c.get("sources") or [], "flags": c.get("flags") or [], "price": c.get("price"),
        "move_24h": c.get("move_24h"), "dtc": (c.get("si") or {}).get("dtc"),
        "trends": (c.get("trends") or {}).get("ratio"), "pattern": c.get("pattern"),
        "pattern_hits": c.get("pattern_hits"), "lex": c.get("lex"), "mcap_b": c.get("mcap_b"), "fb": None, "msg": chat_msg_id, "out": {}})
    return eid


def main_entries(entries):
    """Alerts that were (or could have been) sent to the phone. The paper-only mid track is kept apart."""
    return [e for e in entries if e.get("track") != "mid"]


def mid_entries(entries):
    return [e for e in entries if e.get("track") == "mid"]


def record_mid(j, c, now):
    """Log a paper-only 'mid-size move' candidate. No message is sent for these."""
    eid = f"mid-{c['ticker']}-{now}"
    j["entries"].append({
        "id": eid, "t": now, "ticker": c["ticker"], "track": "mid", "price": c.get("price"),
        "live": c.get("market_live"), "move_24h": c.get("move_24h"), "rel_volume": c.get("rel_volume"),
        "mcap_b": c.get("mcap_b"), "pace": c.get("pace_1h"), "authors": c.get("authors_1h"), "burst": c.get("burst"),
        "fired_main": bool(c.get("fired")), "sources": ["Reddit"], "out": {}})
    return eid


def set_feedback(j, eid, val):
    for e in j["entries"]:
        if e["id"] == eid:
            e["fb"] = val
            return e
    return None


def _evaluate(e, bars, now):
    """Fill outcome fields from hourly bars [(ts,o,h,l,c)]."""
    t0 = e["t"]
    after = [b for b in bars if b[0] >= t0 - 1800]
    if not after:
        return
    if e.get("live") is False:   # market closed at alert time: the first real chance to buy is the next bar
        nxt = [b for b in bars if b[0] >= t0]
        if not nxt:
            return
        after = nxt
        entry = nxt[0][1]
    else:
        entry = e.get("price") or after[0][1]
    if not entry:
        return
    out = e["out"]
    out["entry"] = round(entry, 4)

    def close_at(sec):
        b = [x for x in after if x[0] <= t0 + sec]
        return b[-1][4] if b else None

    for key, sec in (("r1d", DAY), ("r3d", 3 * DAY), ("r10d", 10 * DAY)):
        if now >= t0 + sec and key not in out:
            cp = close_at(sec)
            if cp:
                out[key] = round(cp / entry - 1, 4)
    w3 = [x for x in after if x[0] <= t0 + C.HOLD_DAYS * DAY]
    if w3:
        out["max3d"] = round(max(x[2] for x in w3) / entry - 1, 4)
        out["min3d"] = round(min(x[3] for x in w3) / entry - 1, 4)
    if e.get("track") == "mid":
        _evaluate_mid(e, after, entry, now)
    elif now >= t0 + C.HOLD_DAYS * DAY and "sim" not in out and w3:
        res = None
        for _, _, h, l, _ in w3:            # stop first if both in one bar (conservative)
            if l <= entry * (1 - C.STOP_PCT):
                res = -C.STOP_PCT
                break
            if h >= entry * (1 + C.TP_PCT):
                res = C.TP_PCT
                break
        if res is None:
            res = w3[-1][4] / entry - 1
        out["sim"] = round(res - C.TRADE_COST, 4)
    if now >= t0 + 10 * DAY:
        out["done"] = True


def _simulate(bars, entry, tp, sl, cost):
    for _, _, h, l, _ in bars:          # stop first if both in one bar (conservative)
        if l <= entry * (1 - sl):
            return round(-sl - cost, 4)
        if h >= entry * (1 + tp):
            return round(tp - cost, 4)
    return round(bars[-1][4] / entry - 1 - cost, 4)


def _evaluate_mid(e, after, entry, now):
    """Paper-trade a mid-track entry with every rule in MID_RULES (e.g. sim15 = +15% target)."""
    out, t0 = e["out"], e["t"]
    for tp, sl, days in C.MID_RULES:
        key = f"sim{round(tp * 100)}"
        w = [x for x in after if x[0] <= t0 + days * DAY]
        if now >= t0 + days * DAY and key not in out and w:
            out[key] = _simulate(w, entry, tp, sl, C.MID_COST)


def update_outcomes(j, now, bars_fn, limit=None):
    """Refresh outcomes for alerts that still need data. One price download per ticker."""
    limit = limit or C.MAX_OUTCOME_FETCH
    todo = [e for e in j["entries"] if not e["out"].get("done") and now - e["t"] >= 3600]
    by_tk = {}
    for e in todo:
        by_tk.setdefault(e["ticker"], []).append(e)
    n = 0
    for tk, es in by_tk.items():
        if n >= limit:
            break
        oldest = min(e["t"] for e in es)
        rng = "5d" if now - oldest < 4 * DAY else ("1mo" if now - oldest < 25 * DAY else "3mo")
        bars = bars_fn(tk, rng)
        n += 1
        if bars:
            for e in es:
                _evaluate(e, bars, now)
    return n


def stats(entries):
    ev = [e for e in entries if "max3d" in e["out"]]
    sim = [e["out"]["sim"] for e in entries if "sim" in e["out"]]
    def pct(xs):
        return round(100 * sum(xs) / len(xs)) if xs else None
    return {
        "n": len(entries), "evaluated": len(ev),
        "hit20": pct([e["out"]["max3d"] >= 0.20 for e in ev]),
        "dd15": pct([e["out"]["min3d"] <= -0.15 for e in ev]),
        "sim_n": len(sim), "sim_mean": round(100 * sum(sim) / len(sim), 1) if sim else None,
        "sim_total": round(100 * sum(sim), 1) if sim else None,
        "sim_win": pct([s > 0 for s in sim]),
    }


def breakdown(entries):
    """Stats per source, tier, feedback, and flag — what actually works."""
    groups = {}
    for e in entries:
        keys = [f"מקור: {s}" for s in e["sources"]] + [f"רמה: {e.get('tier')}"]
        if len(e["sources"]) >= 2:
            keys.append("2+ מקורות")
        if e.get("fb") is not None:
            keys.append("👍 שלך" if e["fb"] > 0 else "👎 שלך")
        keys += [f"סימון: {f}" for f in e.get("flags") or []]
        if e.get("channel"):
            keys.append({"push": "📲 התראה מיידית", "extreme": "🚨 פעילות חריגה"}.get(e["channel"], "📋 רשימה יומית"))
        if e.get("pattern") is not None:
            keys.append("🎯 דפוס 4/4" if e["pattern"] == 4 else "🎯 דפוס 3/4" if e["pattern"] == 3 else "דפוס 0-2/4")
        for k in keys:
            groups.setdefault(k, []).append(e)
    return {k: stats(v) for k, v in sorted(groups.items())}


def weekly_due(j, now):
    tm = time.gmtime(now)
    week = time.strftime("%G-W%V", tm)
    return tm.tm_wday == C.WEEKLY_DOW and tm.tm_hour >= C.WEEKLY_HOUR_UTC and j.get("last_weekly") != week, week


def prune(j, now, keep_days=400):
    j["entries"] = [e for e in j["entries"] if now - e["t"] < keep_days * DAY]


def mid_stats(entries):
    """Scorecard for the mid track: how often +10/15/20% came, how often -10%, and each paper rule."""
    ev = [e for e in entries if "max3d" in e["out"]]
    def pct(xs):
        return round(100 * sum(xs) / len(xs)) if xs else None
    res = {"n": len(entries), "evaluated": len(ev),
           "hit10": pct([e["out"]["max3d"] >= 0.10 for e in ev]),
           "hit15": pct([e["out"]["max3d"] >= 0.15 for e in ev]),
           "hit20": pct([e["out"]["max3d"] >= 0.20 for e in ev]),
           "dd10": pct([e["out"]["min3d"] <= -0.10 for e in ev]), "rules": {}}
    for tp, sl, days in C.MID_RULES:
        k = f"sim{round(tp * 100)}"
        xs = [e["out"][k] for e in entries if k in e["out"]]
        res["rules"][k] = {"label": f"+{round(tp * 100)}% / −{round(sl * 100)}% / {days} ימים", "n": len(xs),
                           "mean": round(100 * sum(xs) / len(xs), 1) if xs else None,
                           "win": pct([x > 0 for x in xs]), "total": round(100 * sum(xs), 1) if xs else None}
    return res


def mid_breakdown(entries):
    """Mid-track scorecards per sub-group, so the data can tell which filter adds an edge."""
    vol = C.MID_VOL_MULT
    groups = {
        "כל המסלול": entries,
        f"מחזור פי {vol:g}+": [e for e in entries if (e.get("rel_volume") or 0) >= vol],
        f"מחזור רגיל": [e for e in entries if (e.get("rel_volume") or 0) < vol],
        "המחיר עוד לא זז (<10%)": [e for e in entries if (e.get("move_24h") or 0) < 10],
        "המחיר כבר עלה 10%+": [e for e in entries if (e.get("move_24h") or 0) >= 10],
        "עברה גם את הסף הרגיל": [e for e in entries if e.get("fired_main")],
    }
    return {k: mid_stats(v) for k, v in groups.items() if v}
