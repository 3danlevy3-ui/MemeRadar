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
        "pattern_hits": c.get("pattern_hits"), "lex": c.get("lex"), "fb": None, "msg": chat_msg_id, "out": {}})
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
    if now >= t0 + C.HOLD_DAYS * DAY and "sim" not in out and w3:
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
