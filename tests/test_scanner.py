"""Offline tests: real WSB sample + a synthetic meme burst, network mocked."""
import json, os, random, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scanner import config as C, signals, tickers, notify, main, sources as _src
ORIG_OPTIONS = _src.options_activity

UNI = {"GME", "AMC", "KSS", "BYND", "SPY", "NVDA", "TSLA", "OPEN", "DD", "CEO", "A", "IT", "NOW", "ZZZQ"}
FIX = json.load(open(os.path.join(os.path.dirname(__file__), "fixture_wsb.json")))


def test_extract():
    assert tickers.extract("YOLO into $gme and AMC, DD inside. CEO is IT", UNI) == {"GME", "AMC"}
    assert tickers.extract("the store is open now", UNI) == set()
    assert tickers.extract("$OPEN squeeze", UNI) == {"OPEN"}   # cashtag overrides stopword
    assert tickers.extract("BYND/KSS", UNI) == {"BYND", "KSS"}


def make_items(n, ts0, span, tk=None, authors=50, prefix="x"):
    out = []
    for i in range(n):
        body = f"${tk} to the moon 🚀" if tk else "random chatter about the market"
        out.append({"id": f"{prefix}{i}", "created_utc": ts0 + random.randint(0, span - 1),
                    "author": f"u{random.randint(0, authors - 1)}", "body": body})
    return out


def test_burst_fires_and_quiet_does_not():
    random.seed(1)
    now = int(time.time())
    st = signals.new_state()
    # 3 days of baseline: ~400 items/h, KSS mentioned ~0.2/h
    for h in range(72, 1, -1):
        t0 = now - h * 3600
        items = make_items(400, t0, 3600, prefix=f"b{h}_")
        if h % 5 == 0:
            items += make_items(1, t0, 3600, "KSS", prefix=f"k{h}_")
        signals.ingest(st, items, UNI)
    # last hour: 30 KSS mentions from 20 authors + normal chatter + 3 GME
    last = make_items(400, now - 3600, 3600, prefix="n") + make_items(30, now - 3600, 3600, "KSS", 20, "hot") \
        + make_items(3, now - 3600, 3600, "GME", 3, "g")
    items = signals.ingest(st, last, UNI)
    m, a, tx, tot = signals.window_stats(items, now)
    c = {r["ticker"]: r for r in signals.evaluate(st, m, a, tot, now)}
    assert c["KSS"]["fired"], c["KSS"]
    assert c["KSS"]["burst"] > 20
    assert "GME" not in c or not c["GME"]["fired"]
    # dedupe: ingesting the same items again must not double count
    before = sum(h["T"].get("KSS", 0) for h in st["hours"].values())
    signals.ingest(st, last, UNI)
    assert sum(h["T"].get("KSS", 0) for h in st["hours"].values()) == before


def test_exit_rules():
    now = int(time.time())
    st = signals.new_state()
    st["alerts"]["KSS"] = {"time": now - 10 * 3600, "entry_price": 10, "peak_price": 14, "peak_m6": 100, "score": 70}
    ex = signals.check_exits(st, now, lambda t: {"ok": True, "price": 11.5})
    assert ex and "below the peak" in ex[0]["reason"]
    assert abs(ex[0]["ret"] - 0.15) < 1e-9


def test_real_fixture_runs():
    uni = {"SPY", "NVDA", "TSLA", "AMD", "MU", "INTC", "SMCI", "GLD", "SLV", "OKLO", "RKLB"}
    st = signals.new_state()
    items = signals.ingest(st, FIX["comments"] + FIX["posts"], uni)
    now = max(i["t"] for i in items) + 1
    m, a, tx, tot = signals.window_stats(items, now, 24 * 60)
    assert tot == len(items) > 50
    print("fixture mentions:", dict(m))


def mock_market(trending=None, st_n=5, x=None):
    main.sources.price_context = lambda t: {"ok": True, "price": 10.0, "move_24h": 0.03, "rel_volume": 1.8, "name": t}
    main.sources.stocktwits_trending = lambda: trending or []
    main.sources.stocktwits_stream = lambda t, now=None: {"n_1h": st_n if t == "KSS" else 0, "rate_h": 0.4, "bull": 0.8, "texts": ["$KSS squeeze"]}
    main.sources.short_interest = lambda t: {"short_shares": 30_000_000, "dtc": 8.2, "chg_pct": 2.0, "date": "2026-08-31"}
    main.sources.shares_outstanding = lambda t: 113_000_000
    main.sources.options_activity = lambda t: {"call_vol": 9000, "put_vol": 1500, "cp_ratio": 6.0, "call_vol_oi": 0.9}


def test_format():
    c = {"ticker": "KSS", "score": 77, "tier": "EARLY", "mentions_1h": 30, "burst": 25.0, "authors_1h": 20,
         "price": 10.1, "move_24h": 3.2, "rel_volume": 2.5, "name": "Kohl's Corp"}
    msg = notify.fmt_alert(c, {"sentiment": 0.8, "hype": 9, "squeeze_talk": True, "summary_he": "מדברים על סקוויז"})
    assert "$KSS" in msg and "סקוויז" in msg


def test_full_run_mocked(tmp_path=None, monkeypatch=None):
    import tempfile
    d = tempfile.mkdtemp()
    C.STATE_PATH, C.TICKERS_PATH = f"{d}/state.json", f"{d}/tickers.json"
    json.dump({"symbols": sorted(UNI | {f"T{i:03d}" for i in range(4000)}), "fetched": time.time()}, open(C.TICKERS_PATH, "w"))
    random.seed(2)
    now = int(time.time())

    def fake_fetch(kind, sub, after, before):
        if sub != "wallstreetbets" or kind != "comments":
            return []
        items = make_items(int((before - after) / 3600 * 300), int(after), max(1, int(before - after)), prefix=f"f{after}_")
        if before >= now - 5:
            items += make_items(40, int(after), int(before - after), "KSS", 25, "burst")
        return items
    sent = []
    main.sources.fetch_items = fake_fetch
    mock_market()
    main.notify.send = lambda text: sent.append(text) or True
    C.BACKFILL_HOURS = 30
    main.run()
    assert any("$KSS" in s for s in sent), sent
    st = json.load(open(C.STATE_PATH))
    assert "KSS" in st["alerts"] and st["backfilled"]
    # second run immediately: cooldown -> no duplicate alert
    n = len(sent); main.run(); assert len(sent) == n
    print(sent[0])


def fresh_dirs():
    import tempfile
    d = tempfile.mkdtemp()
    C.STATE_PATH, C.TICKERS_PATH = f"{d}/state.json", f"{d}/tickers.json"
    json.dump({"symbols": sorted(UNI | {f"T{i:03d}" for i in range(4000)}), "fetched": time.time()}, open(C.TICKERS_PATH, "w"))


def quiet_reddit(before_now_burst=False):
    now = int(time.time())
    def f(kind, sub, after, before):
        if sub != "wallstreetbets" or kind != "comments":
            return []
        return make_items(int((before - after) / 3600 * 300), int(after), max(1, int(before - after)), prefix=f"q{after}_")
    main.sources.fetch_items = f


def test_stocktwits_only_trigger():
    random.seed(3); fresh_dirs(); quiet_reddit(); C.BACKFILL_HOURS = 30
    sent = []; main.notify.send = lambda text: sent.append(text) or True
    tr = [{"ticker": "KSS", "rank": 3, "score": 9.1, "mcap_musd": 2000, "float_m": 110, "shares_m": 113,
           "summary": "Squeeze talk after earnings", "cls": "Stock"},
          {"ticker": "AMD", "rank": 1, "score": 12, "mcap_musd": 300000, "float_m": 1600, "shares_m": 1600, "summary": "", "cls": "Stock"}]
    mock_market(trending=tr, st_n=25)
    main.run()
    kss = [s for s in sent if "$KSS" in s]
    assert kss and "Stocktwits" in kss[0] and "⛽" in kss[0], sent
    assert not any("$AMD" in s for s in sent)          # mega cap filtered
    st = json.load(open(C.STATE_PATH)); assert st["st_prev"] == ["KSS", "AMD"]


def test_multi_source_and_x_budget():
    random.seed(4); fresh_dirs(); C.BACKFILL_HOURS = 30
    now = int(time.time())
    def f(kind, sub, after, before):
        if sub != "wallstreetbets" or kind != "comments":
            return []
        items = make_items(int((before - after) / 3600 * 300), int(after), max(1, int(before - after)), prefix=f"m{after}_")
        if before >= now - 5:
            items += make_items(40, int(after), int(before - after), "KSS", 25, "burst")
        return items
    main.sources.fetch_items = f
    mock_market(st_n=25)
    calls = {"counts": 0}
    from scanner import xsource
    class R:
        def __init__(s, j): s.status_code, s._j, s.text = 200, j, ""
        def json(s): return s._j
    def fake_get(url, params=None, timeout=None, headers=None):
        if "counts" in url:
            calls["counts"] += 1
            return R({"data": [{"tweet_count": 3}] * 160 + [{"tweet_count": 400}, {"tweet_count": 50}]})
        if "users/by" in url:
            return R({"data": {"id": "42"}})
        return R({"data": [{"id": "900", "text": "gm $KSS"}]})
    xsource.requests.get = fake_get
    C.X_BEARER_TOKEN, C.X_DAILY_BUDGET = "t", 0.06
    sent = []; main.notify.send = lambda text: sent.append(text) or True
    main.run()
    k = [s for s in sent if "$KSS" in s and "ציון" in s]
    assert k and "Reddit + Stocktwits + X" in k[0], sent
    st = json.load(open(C.STATE_PATH))
    assert st["x"]["spent"] <= 0.06 + 1e-9 and st["x"]["since"]["TheRoaringKitty"] == "900"
    # second run: influencer post is now "new" -> influencer message
    main.sources.fetch_items = quiet_reddit() or main.sources.fetch_items
    main.run()
    assert any("TheRoaringKitty" in s for s in sent)
    C.X_BEARER_TOKEN = ""


def test_options_parser():
    rows = [{"expirygroup": "Sep 25"}, {"expirygroup": "", "c_Volume": "1,200", "p_Volume": "300", "c_Openinterest": "1000"},
            {"expirygroup": "", "c_Volume": "--", "p_Volume": "100", "c_Openinterest": "500"},
            {"expirygroup": "Oct 2"}, {"expirygroup": "", "c_Volume": "10", "p_Volume": "0", "c_Openinterest": "0"},
            {"expirygroup": "Oct 9"}, {"expirygroup": "", "c_Volume": "99999", "p_Volume": "0", "c_Openinterest": "0"}]
    class R:
        def json(s): return {"data": {"table": {"rows": rows}}}
    from scanner import sources
    old = sources.S.get; sources.S.get = lambda *a, **k: R()
    o = ORIG_OPTIONS("KSS"); sources.S.get = old
    assert o["call_vol"] == 1210 and o["put_vol"] == 400 and abs(o["call_vol_oi"] - 1210 / 1500) < 1e-9


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f(); print("ok", k)
