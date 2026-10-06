"""MemeRadar live scan. Run every ~15 minutes: python -m scanner.main"""
import argparse
import json
import os
import time

from . import config as C
from . import bot, charts, dashboard, journal, llm, notify, plain, signals, sources
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


def earnings_soon(state, now):
    """Tickers with earnings yesterday/today/tomorrow (US calendar dates). Cached per day."""
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    e = state.get("earn") or {}
    if e.get("day") == day:
        return set(e.get("set", []))
    out, ok = set(), False
    for off in (-1, 0, 1):
        r = sources.earnings_on(time.strftime("%Y-%m-%d", time.gmtime(now + off * 86400)))
        if r is not None:
            ok = True
            out |= r
    health(state, "earnings", ok)
    if ok:
        state["earn"] = {"day": day, "set": sorted(out)}
    return out


def maybe_daily_health(state, now, send):
    h = state.setdefault("health", {"day": "", "src": {}})
    today = time.strftime("%Y%m%d", time.gmtime(now))
    if time.gmtime(now).tm_hour < C.HEALTH_HOUR_UTC or h.get("day") == today:
        return
    broken = [k for k, (ok, bad) in h.get("src", {}).items() if bad and not ok]
    if broken:   # stay silent when everything works; problems also appear in the daily digest
        send(notify.fmt_health(h["src"], state.get("x", {}), sum(1 for a in state["alerts"].values() if not a.get("closed"))))
    state["health_yesterday"] = h.get("src", {})
    h.update(day=today, src={})


def maybe_digest(state, now, send):
    """Once a day, before the US open: the stocks that warmed up but did not earn an instant alert."""
    day = time.strftime("%Y%m%d", time.gmtime(now))
    if time.gmtime(now).tm_hour < C.DIGEST_HOUR_UTC or state.get("digest_day") == day:
        return
    d = state.get("digest", {})
    items = [dict(v, hot=now - v["last"] < 2 * 3600) for v in d.values() if now - v["last"] < 24 * 3600]
    items.sort(key=lambda v: (-v["hot"], -v["score"]))
    src = (state.get("health") or {}).get("src", {})
    problems = [k for k, (ok, bad) in src.items() if bad and not ok]
    send(plain.fmt_digest(items, problems, C.PAGES_URL))
    state["digest"] = {}
    state["digest_day"] = day



def _where(ex):
    """Short error text plus the code line where it happened, for /status."""
    import traceback
    tb = traceback.extract_tb(ex.__traceback__)
    at = f" @ {tb[-1].filename.split('/')[-1]}:{tb[-1].lineno}" if tb else ""
    return (repr(ex)[:160] + at)[:200]

def run(dry=False, verbose=False):
    now = int(time.time())
    state = load_json(C.STATE_PATH, None) or signals.new_state()
    jr = load_json(C.JOURNAL_PATH, None) or journal.new_journal()

    def send(text, buttons=None, photo=None, urgent=False):
        """Send now, or hold while /quiet is on. Returns message_id when sent."""
        if dry:
            print(text, "[buttons]" if buttons else "", f"[photo {len(photo)}b]" if photo else "")
            return None
        if not urgent and state.get("quiet_until", 0) > time.time():
            state.setdefault("held", []).append(text)
            return None
        mid = notify.send(text, buttons)
        if photo:
            notify.send_photo(photo)
        return mid

    def weekly(force=False):
        due, week = journal.weekly_due(jr, now)
        if not (due or force):
            return
        main_e = journal.main_entries(jr["entries"])
        wk = [e for e in main_e if now - e["t"] < 7 * 86400]
        groups = journal.breakdown(main_e)
        text = notify.fmt_weekly(journal.stats(wk), journal.stats(main_e), groups,
                                 sorted(wk, key=lambda e: -(e.get("score") or 0)), C.PAGES_URL,
                                 mid=journal.mid_breakdown(journal.mid_entries(jr["entries"])))
        png = charts.weekly_chart(main_e, groups) if C.USE_CHARTS else None
        send(text, photo=png, urgent=force)
        if not force:
            jr["last_weekly"] = week

    # Scans can silently not happen (e.g. GitHub had no machine to run them). Our code cannot report
    # that while it is not running, so the first scan afterwards says how long the gap was.
    try:
        last = state.get("last_run") or 0
        if last and now - last > C.GAP_ALERT_MIN * 60:
            send(notify.fmt_gap(last, now), urgent=True)
    except Exception as ex:  # keep scanning even if this part breaks
        print("gap notice error", repr(ex))

    try:
        if not dry:
            bot.poll(state, jr, weekly)
    except Exception as ex:  # keep scanning even if this part breaks
        print("telegram error", repr(ex))
        health(state, "errors", False)
        state.setdefault("last_errors", []).append([now, "telegram", repr(ex)[:200]])
        state["last_errors"] = state["last_errors"][-10:]
    uni = universe()
    if not uni:
        print("no ticker universe; abort")
        return

    # ---------------- Reddit
    # Build the baseline gradually: each run backfills older hours for at most BACKFILL_BUDGET_S,
    # newest first, so no single run can hit the GitHub time limit.
    if not state.get("backfilled"):
        target = now - C.BACKFILL_HOURS * 3600
        cursor = state.get("backfill_cursor") or (now - C.LOOKBACK_MIN * 60)
        deadline = time.time() + C.BACKFILL_BUDGET_S
        n = 0
        while cursor > target and time.time() < deadline:
            a = max(target, cursor - 3600)
            signals.ingest(state, fetch_window(a, cursor), uni)
            state["seen"] = {k: v for k, v in state["seen"].items() if v >= now - 3 * 3600}
            cursor, n = a, n + 1
        state["backfill_cursor"] = cursor
        state["backfilled"] = cursor <= target
        print(f"backfill: +{n} hours, {round((now - cursor) / 3600)}h of history"
              f"{' (done)' if state['backfilled'] else ''}")
    items = signals.ingest(state, fetch_window(now - C.LOOKBACK_MIN * 60, now), uni)
    health(state, "reddit", bool(items))
    m60, a60, texts, total60 = signals.window_stats(items, now, C.LOOKBACK_MIN)
    m20, _, _, _ = signals.window_stats(items, now, 20)
    reddit = {c["ticker"]: c for c in signals.evaluate(state, m60, a60, total60, now, m20)}

    # candidate pool: Reddit burst + near-misses
    pool = {t: {"ticker": t} for t, c in reddit.items() if c["fired"]}
    for c in sorted(reddit.values(), key=lambda c: -c["score"])[:5]:
        pool.setdefault(c["ticker"], {"ticker": c["ticker"]})

    for t in state.get("watch", []):
        pool.setdefault(t, {"ticker": t})["watch_user"] = True
    qual = signals.quality(items, now, C.LOOKBACK_MIN)
    earn = earnings_soon(state, now) if C.USE_EARNINGS else set()

    # ---------------- Stocktwits trending
    trending = {}
    try:
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
    except Exception as ex:  # keep scanning even if this part breaks
        print("stocktwits error", repr(ex))
        health(state, "errors", False)
        state.setdefault("last_errors", []).append([now, "stocktwits", repr(ex)[:200]])
        state["last_errors"] = state["last_errors"][-10:]

    # ---------------- X: watched accounts (the Roaring-Kitty case) + watchlist rotation
    xc = XClient(state)
    try:
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
    except Exception as ex:  # keep scanning even if this part breaks
        print("x error", repr(ex))
        health(state, "errors", False)
        state.setdefault("last_errors", []).append([now, "x", repr(ex)[:200]])
        state["last_errors"] = state["last_errors"][-10:]

    # ---------------- enrich every candidate with Stocktwits + X
    x_left = C.X_MAX_PER_RUN
    order = sorted(pool, key=lambda t: -(reddit.get(t, {}).get("score", 0) + (20 if t in trending else 0)))
    for t in order[:15]:
        try:
            c = pool[t]
            r = reddit.get(t)
            if r:
                c.update({k: r[k] for k in ("mentions_1h", "pace_1h", "authors_1h", "burst", "baseline_h", "fast")})
                c["reddit_fired"] = r["fired"]
                c["reddit_new"] = r["baseline_h"] < C.MIN_BASELINE or r.get("history_h", 0) < C.MIN_HISTORY_HOURS
            if C.USE_STOCKTWITS:
                st = sources.stocktwits_stream(t, now)
                ema = state.get("st_rate", {}).get(t)
                fired, burst, st_new = signals.st_signal(st, ema, bool(trending.get(t, {}).get("new")),
                                                         state.get("st_obs", {}).get(t, 0))
                signals.st_update(state, t, st, fired)
                if st:
                    c.update(st_fired=fired, st_burst=burst, st_new=st_new, st_1h=st["n_1h"], st_bull=st["bull"],
                             st_rank=trending.get(t, {}).get("rank"), st_summary=trending.get(t, {}).get("summary"))
                    c["_st_texts"] = st["texts"]
            if xc.ok and (c.get("watch") or (x_left > 0 and (c.get("reddit_fired") or c.get("st_fired")))):
                if not c.get("watch"):
                    x_left -= 1
                cnt = xc.counts(t)
                fired, burst = signals.x_signal(cnt)
                if cnt:
                    c.update(x_fired=fired, x_burst=burst, x_1h=cnt["x_1h"], x_24h=cnt["x_24h"])
        except Exception as ex:  # one bad stock or source must never stop the whole scan
            print("enrich error", t, repr(ex))
            health(state, "errors", False)
            state.setdefault("last_errors", []).append([now, "enrich " + str(t), _where(ex)])
            state["last_errors"] = state["last_errors"][-10:]
    if xc.ok or C.X_BEARER_TOKEN:
        health(state, "x", xc.errors == 0)

    # ---------------- decide, enrich with market structure, alert
    sent = 0
    for t, c in pool.items():
        try:
            if not (c.get("reddit_fired") or c.get("st_fired") or c.get("x_fired") or c.get("influencer")):
                continue
            signals.fuse(c)
            if not signals.should_alert(state, c, now):
                continue
            px = sources.price_context(t)
            health(state, "yahoo", px.get("ok"))
            if px.get("ok"):
                c.update(price=round(px["price"], 4), move_24h=round(px["move_24h"] * 100, 1),
                         rel_volume=round(px["rel_volume"], 1) if px.get("rel_volume") else None, name=px.get("name"),
                         market_live=px.get("live"), etf=px.get("etf"), dollar_vol_m=px.get("dollar_vol_m"))
            sh = cached(state, "shares", t, 24 * 7, sources.shares_outstanding)
            if sh and c.get("price"):
                c["mcap_b"] = round(sh * c["price"] / 1e9, 1)
            if signals.too_big(c) and not c.get("influencer"):
                if verbose:
                    print(t, "-> skipped:", signals.too_big(c))
                continue
            if C.USE_SHORT_INTEREST:
                c["si"] = cached(state, "si", t, 12, sources.short_interest)
                if c["si"] and sh:
                    c["si"]["pct_out"] = round(100 * c["si"]["short_shares"] / sh, 1)
                health(state, "finra", c["si"] is not None)
            if C.USE_OPTIONS:
                c["options"] = sources.options_activity(t)
                health(state, "nasdaq", c["options"] is not None)
            signals.fuse(c)
            if C.USE_TRENDS:
                c["trends"] = cached(state, "trends", t, 3, sources.google_trends)
                health(state, "google_trends", c["trends"] is not None)
            signals.apply_flags(c, qual.get(t), t in earn, c.get("trends"))
            signals.pattern(c, state, journal.main_entries(jr["entries"]), now)
            all_texts = texts.get(t, []) + c.pop("_st_texts", [])
            c["lex"] = signals.lexicon(all_texts)
            analysis = llm.analyse(t, all_texts)
            if analysis and analysis.get("pump_suspect") and (analysis.get("dd_quality") or 0) <= 2:
                c["score"] = max(0, c["score"] - 15)
            if verbose:
                print({k: v for k, v in c.items() if not k.startswith("_")})
            ch, why_ch = signals.channel(c, state, now)
            if ch == "skip":
                continue
            c["channel"] = ch
            eid = journal.record(jr, c, now)
            jr["entries"][-1]["channel"] = ch
            if verbose:
                print(t, "->", ch, why_ch)
            if ch == "digest":
                why, plus, minus = plain.reasons(c, analysis)
                d = state.setdefault("digest", {})
                prev_d = d.get(t, {})
                d[t] = {"ticker": t, "name": c.get("name"), "score": max(c["score"], prev_d.get("score", 0)),
                        "why": (why[0] if why else "") + (f" · {minus[0]}" if minus else ""),
                        "first": prev_d.get("first", now), "last": now, "n": prev_d.get("n", 0) + 1}
                continue
            png = None
            if C.USE_CHARTS:
                bars = sources.price_bars(t, "5d")
                png = charts.alert_chart(t, charts.hourly_mentions(state, t, now), bars,
                                         (c.get("trends") or {}).get("series"), now)
            technical = notify.fmt_alert(c, analysis).replace(f"<i>{notify.HIST}</i>", "").strip()
            jr["entries"][-1]["msg"] = send(plain.fmt_alert(c, analysis, technical, extreme=(ch == "extreme")),
                                            bot.feedback_buttons(eid), png, urgent=(ch == "extreme"))
            prev = state["alerts"].get(t, {})
            state["alerts"][t] = {
                "time": now, "tier": c["tier"], "score": c["score"], "sources": c["sources"],
                "entry_price": prev.get("entry_price") if prev and not prev.get("closed") else c.get("price"),
                "peak_price": c.get("price"), "peak_m6": signals.recent_sum(state, t, now, 6)}
            sent += 1
        except Exception as ex:  # one bad stock or source must never stop the whole scan
            print("alert error", t, repr(ex))
            health(state, "errors", False)
            state.setdefault("last_errors", []).append([now, "alert " + str(t), _where(ex)])
            state["last_errors"] = state["last_errors"][-10:]

    # ---------------- mid-size moves track: paper only, never messages the phone
    try:
        if C.MID_ENABLED:
            mids = journal.mid_entries(jr["entries"])
            last_mid = {x["ticker"]: x["t"] for x in mids}
            left = min(C.MID_PER_RUN, C.MID_MAX_PER_DAY - sum(1 for x in mids if now - x["t"] < 86400))
            cands = sorted((r for r in reddit.values()
                            if r["ticker"] not in C.MEGA and r["pace_1h"] >= C.MID_MIN_PACE
                            and r["authors_1h"] >= C.MID_MIN_AUTHORS and r["burst"] >= C.MID_BURST
                            and now - last_mid.get(r["ticker"], 0) >= C.MID_COOLDOWN_H * 3600),
                           key=lambda r: -r["score"])
            for r in cands:
                if left <= 0:
                    break
                left -= 1
                px = sources.price_context(r["ticker"])
                if not px.get("ok"):
                    continue
                sh = cached(state, "shares", r["ticker"], 24 * 7, sources.shares_outstanding)
                size = dict(ticker=r["ticker"], etf=px.get("etf"), dollar_vol_m=px.get("dollar_vol_m"),
                            mcap_b=round(sh * px["price"] / 1e9, 1) if sh else None)
                if signals.too_big(size):
                    continue
                journal.record_mid(jr, dict(r, price=round(px["price"], 4), move_24h=round(px["move_24h"] * 100, 1),
                                            rel_volume=round(px["rel_volume"], 1) if px.get("rel_volume") else None,
                                            market_live=px.get("live")), now)
    except Exception as ex:  # keep scanning even if this part breaks
        print("mid track error", repr(ex))
        health(state, "errors", False)
        state.setdefault("last_errors", []).append([now, "mid", _where(ex)])
        state["last_errors"] = state["last_errors"][-10:]

    try:
        for x in signals.check_exits(state, now, sources.price_context):
            send(plain.fmt_exit(x))
        maybe_daily_health(state, now, send)
        maybe_digest(state, now, send)
    except Exception as ex:  # keep scanning even if this part breaks
        print("exits/digest error", repr(ex))
        health(state, "errors", False)
        state.setdefault("last_errors", []).append([now, "exits/digest", repr(ex)[:200]])
        state["last_errors"] = state["last_errors"][-10:]

    # ---------------- journal outcomes, weekly report, held messages, dashboard
    try:
        journal.update_outcomes(jr, now, sources.price_bars)
        weekly()
        if state.get("held") and state.get("quiet_until", 0) <= time.time():
            held = state.pop("held")
            send(f"🔔 <b>בזמן ההשתקה ({len(held)} הודעות):</b>\n\n" + "\n\n———\n\n".join(held)[:3800])
    except Exception as ex:  # keep scanning even if this part breaks
        print("journal/weekly error", repr(ex))
        health(state, "errors", False)
        state.setdefault("last_errors", []).append([now, "journal/weekly", repr(ex)[:200]])
        state["last_errors"] = state["last_errors"][-10:]
    journal.prune(jr, now)
    try:
        dashboard.build(jr, state, now)
    except Exception as ex:  # the dashboard must never break the scan
        print("dashboard error", ex)

    signals.prune(state, now)
    for kind, entries in (state.get("cache") or {}).items():   # drop cache older than 8 days
        state["cache"][kind] = {k: v for k, v in entries.items() if now - v[0] < 8 * 86400}
    state["last_run"] = now
    save_json(C.STATE_PATH, state)
    save_json(C.JOURNAL_PATH, jr)
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
        try:
            run(dry=args.dry, verbose=args.verbose)
        except Exception:
            import traceback
            traceback.print_exc()
            try:   # tell the phone, at most once every 6 hours
                st = load_json(C.STATE_PATH, {}) or {}
                if time.time() - st.get("last_crash_note", 0) > 6 * 3600:
                    import sys as _s
                    err = repr(_s.exc_info()[1])[:300]
                    notify.send("⚠️ הסורק נתקל בשגיאה ולא סיים את הריצה.\nהעבירו את השורה הזו ל-Claude:\n<code>"
                                + notify.e(err) + "</code>")
                    st["last_crash_note"] = time.time()
                    save_json(C.STATE_PATH, st)
            except Exception:
                pass
            raise
