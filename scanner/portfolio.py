"""Virtual portfolio: $BOOK_USD into every signal, managed by the experiment rules (journal.position)."""
import calendar
import time

from . import config as C

BOOKS = {
    "phone": "התראות לטלפון",
    "all": "כל האותות (כולל הרשימה היומית)",
    "mid": "מסלול 10%–20%",
}


def _start():
    try:
        return calendar.timegm(time.strptime(C.BOOK_START, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return 0


def _member(e, book):
    if book == "mid":
        return e.get("track") == "mid"
    if e.get("track") == "mid":
        return False
    if book == "phone":
        return e.get("channel") in ("push", "extreme")
    return True


def build(entries, now=None):
    """{book: {"positions": [...], "summary": {...}, "curve": [[t, pnl$], ...]}}"""
    now = now or int(time.time())
    start = _start()
    out = {}
    for book, label in BOOKS.items():
        rows, busy = [], {}
        for e in sorted((x for x in entries if x["t"] >= start and _member(x, book)), key=lambda x: x["t"]):
            t = e["ticker"]
            if busy.get(t, 0) > e["t"]:
                continue                       # already holding this stock: no second $1,000 into it
            pos = e.get("pos") or {}
            entry = pos.get("entry") or e.get("price")
            if not entry:
                continue
            status = pos.get("status") or "open"
            busy[t] = pos.get("exit_t") or (pos.get("until") or e["t"] + 3 * 86400) if status == "closed" else 10 ** 12
            ret = pos.get("ret")
            rows.append({
                "ticker": t, "t": e["t"], "entry": entry, "tp": pos.get("tp"), "sl": pos.get("sl"),
                "until": pos.get("until") or e["t"] + (C.MID_BOOK_RULE[2] if book == "mid" else C.HOLD_DAYS) * 86400,
                "status": status, "reason": pos.get("reason"),
                "now": pos.get("exit") or pos.get("last"), "now_t": pos.get("exit_t") or pos.get("last_t"),
                "ret": ret, "pnl": round(C.BOOK_USD * ret, 2) if ret is not None else None,
                "flags": [f.split(":")[0] for f in e.get("flags") or []][:3], "score": e.get("score"),
            })
        closed = [r for r in rows if r["status"] == "closed" and r["pnl"] is not None]
        opened = [r for r in rows if r["status"] != "closed"]
        realized = round(sum(r["pnl"] for r in closed), 2)
        unreal = round(sum(r["pnl"] or 0 for r in opened), 2)
        invested = len(rows) * C.BOOK_USD
        curve, acc = [], 0.0
        for r in sorted(closed, key=lambda r: r["now_t"] or r["t"]):
            acc += r["pnl"]
            curve.append([r["now_t"] or r["t"], round(acc, 2)])
        if opened:
            curve.append([now, round(acc + unreal, 2)])
        out[book] = {
            "label": label, "positions": sorted(rows, key=lambda r: (r["status"] == "closed", -r["t"])),
            "curve": curve,
            "summary": {"n": len(rows), "open": len(opened), "closed": len(closed), "invested": invested,
                        "at_work": len(opened) * C.BOOK_USD, "realized": realized, "unrealized": unreal,
                        "total": round(realized + unreal, 2),
                        "total_pct": round((realized + unreal) / invested * 100, 1) if invested else None,
                        "win": round(sum(1 for r in closed if r["pnl"] > 0) / len(closed) * 100) if closed else None,
                        "targets": sum(1 for r in closed if r["reason"] == "target"),
                        "stops": sum(1 for r in closed if r["reason"] == "stop"),
                        "timeouts": sum(1 for r in closed if r["reason"] == "time")},
        }
    return out
