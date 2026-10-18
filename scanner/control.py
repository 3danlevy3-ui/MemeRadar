"""Control group: a few random small caps a day, logged and paper-traded exactly like the alerts.
If the alerts are no better than these, the signal is luck. Added 18 Oct 2026."""
import random
import time

from . import config as C
from . import journal


def eligible(px):
    """Same kind of stock the scanner alerts on: a tradeable small cap that has not already run."""
    if not px.get("ok") or px.get("etf") or not px.get("regular"):
        return False
    if (px.get("price") or 0) < 1:
        return False
    dv = px.get("dollar_vol_m") or 0
    if dv < 1 or dv >= C.BIG_DOLLAR_VOL_M:
        return False
    return abs(px.get("move_24h") or 0) < C.EARLY_MAX_MOVE


def daily(jr, state, universe, price_fn, now=None, rng=None):
    """Once per trading day, during the regular session, log CONTROL_PER_DAY random stocks. Returns how many."""
    now = now or int(time.time())
    day = time.strftime("%Y%m%d", time.gmtime(now))
    st = state.setdefault("control", {})
    if st.get("day") == day and st.get("n", 0) >= C.CONTROL_PER_DAY:
        return 0
    if st.get("day") != day:
        st.update(day=day, n=0, tries=0)
    if st["tries"] >= C.CONTROL_MAX_TRIES:
        return 0
    rng = rng or random.Random()
    pool = sorted(t for t in universe if t.isalpha() and len(t) <= 4 and t not in C.MEGA)
    taken = {e["ticker"] for e in journal.control_entries(jr["entries"]) if now - e["t"] < 30 * 86400}
    added = spins = 0
    while st["n"] < C.CONTROL_PER_DAY and st["tries"] < C.CONTROL_MAX_TRIES and pool and spins < 500:
        spins += 1
        t = rng.choice(pool)
        if t in taken:
            continue
        st["tries"] += 1
        px = price_fn(t)
        if not px.get("ok"):
            continue
        if not px.get("regular"):
            st["tries"] -= 1          # market shut: try again at a later scan
            return added
        if not eligible(px):
            continue
        journal.record_control(jr, {"ticker": t, "price": round(px["price"], 4), "market_regular": True,
                                    "move_24h": round(px["move_24h"] * 100, 1),
                                    "rel_volume": round(px["rel_volume"], 1) if px.get("rel_volume") else None}, now)
        taken.add(t)
        st["n"] += 1
        added += 1
    return added
