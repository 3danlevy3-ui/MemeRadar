"""MemeRadar live scan. Run every ~15 minutes: python -m scanner.main"""
import argparse
import json
import os
import time

from . import config as C
from . import llm, notify, signals, sources
from .tickers import extract
from .xsource import XClient


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def universe():
    u = load_json(C.TICKERS_PATH, {})
    if not u.get("symbols") or time.time() - u.get("fetched", 0) > 7 * 86400:
        syms = sources.load_universe()
        if len(syms) > 3000:
            u = {"symbols": syms, "fetched": time.time()}
            save_json(C.TICKERS_PATH, u)
    return set(u.get("symbols", []))


def fetch_window(after, before):
    items = []
    for sub in C.SUBREDDITS:
        for kind in ("comments", "posts"):
            items += sources.fetch_items(kind, sub, after, before)
    return items


def health(state, source, ok):
    h = state.setdefault("health", {"day": "", "src": {}})
    rec = h["src"].setdefault(source, [0, 0])
    rec[0 if ok else 1] += 1


def cached(state, kind, ticker, ttl_h, fn):
    c = state.setdefault("cache", {}).setdefault(kind, {})
    hit = c.get(ticker)
    if hit and time.time() - hit[0] < ttl_h * 3600:
        return hit[1]
    val = fn(ticker)
    c[ticker] = [time.time(), val]
    return val


def maybe_daily_health(state, now, send):
    h = state.setdefault("health", {"day": "", "src": {}})
    today = time.strftime("%Y%m%d", time.gmtime(now))
    if time.gmtime(now).tm_hour < C.HEALTH_HOUR_UTC or h.get("day") == today:
        return
    if h.get("src"):
        send(notify.fmt_health(h["src"], state.get("x", {}), sum(1 for a in state["alerts"].values() if not a.get("closed"))))
    h.update(day=today, src={})


def run(dry=False, verbose=False):
    now = int(time.time())
    state = load_json(C.STATE_PATH, None) or signals.new_state()
    send = print if dry else notify.send
    uni = universe()
    if not uni:
        print("no ticker universe; abort")
        return

    # ---------------- Reddit
    if not state.get("backfilled"):
        start, stop = now - C.BACKFILL_HOURS * 3600, now - C.LOOKBACK_MIN * 60
        for a in range(start, stop, 3600):
            signals.ingest(state, fetch_window(a, min(a + 3600, stop)), uni)
            state["seen"] = {}
        state["backfilled"] = True
        print(f"backfill done: {len(state['hours'])} hours")
    items = signals.ingest(state, fetch_window(now - C.LOOKBACK_MIN * 60, now), uni)
    health(state, "reddit", bool(items))
    m60, a60, texts, total60 = signals.window_stats(items, now, C.LOOKBACK_MIN)
    reddit = {c["ticker"]: c for c in signals.evaluate(state, m60, a60, total60, now)}

    # candidate pool: Reddit burst + near-misses
    pool = {t: {"ticker": t} for t, c in reddit.items() if c["fired"]}
    for c in sorted(reddit.values(), key=lambda c: -c["score"])[:5]:
        pool.setdefault(c["ticker"], {"ticker": c["ticker"]})

    # ---------------- Stocktwits trending
    trending = {}
    if C.USE_STOCKTWITS:
        tr = sources.stocktwits_trending()
        health(state, "stocktwits", tr is not None)
        prev_top = set(state.get("st_prev", []))
        for s in tr or []:
            t = s["ticker"]
            if t in C.MEGA or (s["cls"] and s["cls"] != "Stock") or (s["mcap_musd"] and s["mcap_musd"] > C.MAX_MCAP_MUSD):
                continue
            s["new"] = s["rank"] <= C.ST_TOP_RANK and t not in prev_top
            trending[t] = s
            if s["new"]:
                pool.setdefault(t, {"ticker": t})
        if tr is not None:
            state["st_prev"] = [s["ticker"] for s in tr if (s["rank"] or 99) <= C.ST_TOP_RANK]

    # ---------------- X: watched accounts (the Roaring-Kitty case) + watchlist rotation
    xc = XClient(state)
    if xc.ok:
        for acct in C.X_ACCOUNTS:
            for p in xc.account_posts(acct.strip()):
                tks = extract(p.get("text", ""), uni) or set()
                send(notify.fmt_influencer(acct, p, tks))
                for t in tks:
                    pool.setdefault(t, {"ticker": t})["influencer"] = acct
        w = xc.next_watch()
        if w:
            pool.setdefault(w, {"ticker": w})["watch"] = True

    # ---------------- enrich every candidate with Stocktwits + X
    x_left = C.X_MAX_PER_RUN
    order = sorted(pool, key=lambda t: -(reddit.get(t, {}).get("score", 0) + (20 if t in trending else 0)))
    for t in order[:15]:
        c = pool[t]
        r = reddit.get(t)
        if r:
            c.update({k: r[k] for k in ("mentions_1h", "authors_1h", "burst", "baseline_h")})
            c["reddit_fired"] = r["fired"]
        if C.USE_STOCKTWITS:
            st = sources.stocktwits_stream(t, now)
            ema = state.get("st_rate", {}).get(t)
            fired, burst = signals.st_signal(st, ema, bool(trending.get(t, {}).get("new")))
            signals.st_update(state, t, st, fired)
            if st:
                c.update(st_fired=fired, st_burst=burst, st_1h=st["n_1h"], st_bull=st["bull"],
                         st_rank=trending.get(t, {}).get("rank"), st_summary=trending.get(t, {}).get("summary"))
                c["_st_texts"] = st["texts"]
        if xc.ok and (c.get("watch") or (x_left > 0 and (c.get("reddit_fired") or c.get("st_fired")))):
            if not c.get("watch"):
                x_left -= 1
            cnt = xc.counts(t)
            fired, burst = signals.x_signal(cnt)
            if cnt:
                c.update(x_fired=fired, x_burst=burst, x_1h=cnt["x_1h"], x_24h=cnt["x_24h"])
    if xc.ok or C.X_BEARER_TOKEN:
        health(state, "x", xc.errors == 0)

    # ---------------- decide, enrich with market structure, alert
    sent = 0
    for t, c in pool.items():
        if not (c.get("reddit_fired") or c.get("st_fired") or c.get("x_fired") or c.get("influencer")):
            continue
        signals.fuse(c)
        if not signals.should_alert(state, c, now):
            continue
        px = sources.price_context(t)
        health(state, "yahoo", px.get("ok"))
        if px.get("ok"):
            c.update(price=round(px["price"], 4), move_24h=round(px["move_24h"] * 100, 1),
                     rel_volume=round(px["rel_volume"], 1) if px.get("rel_volume") else None, name=px.get("name"))
        if C.USE_SHORT_INTEREST:
            c["si"] = cached(state, "si", t, 12, sources.short_interest)
            sh = cached(state, "shares", t, 24 * 7, sources.shares_outstanding)
            if c["si"] and sh:
                c["si"]["pct_out"] = round(100 * c["si"]["short_shares"] / sh, 1)
            health(state, "finra", c["si"] is not None)
        if C.USE_OPTIONS:
            c["options"] = sources.options_activity(t)
            health(state, "nasdaq", c["options"] is not None)
        signals.fuse(c)
        analysis = llm.analyse(t, texts.get(t, []) + c.pop("_st_texts", []))
        if analysis and analysis.get("pump_suspect") and (analysis.get("dd_quality") or 0) <= 2:
            c["score"] = max(0, c["score"] - 15)
        if verbose:
            print({k: v for k, v in c.items() if not k.startswith("_")})
        send(notify.fmt_alert(c, analysis))
        prev = state["alerts"].get(t, {})
        state["alerts"][t] = {
            "time": now, "tier": c["tier"], "score": c["score"], "sources": c["sources"],
            "entry_price": prev.get("entry_price") if prev and not prev.get("closed") else c.get("price"),
            "peak_price": c.get("price"), "peak_m6": signals.recent_sum(state, t, now, 6)}
        sent += 1

    for x in signals.check_exits(state, now, sources.price_context):
        send(notify.fmt_exit(x))
    maybe_daily_health(state, now, send)

    signals.prune(state, now)
    state["last_run"] = now
    save_json(C.STATE_PATH, state)
    print(f"scan ok: {total60} reddit items/{C.LOOKBACK_MIN}m, pool {len(pool)}, {sent} alerts, "
          f"X spent today ${state.get('x', {}).get('spent', 0):.3f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="print alerts instead of sending")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--test-telegram", action="store_true")
    args = ap.parse_args()
    if args.test_telegram:
        print("sent" if notify.send("✅ MemeRadar מחובר. התראות יגיעו לכאן.") else "failed")
    else:
        run(dry=args.dry, verbose=args.verbose)
