"""Data sources: Reddit via the Arctic Shift archive API (near real-time), prices via Yahoo."""
import time

import requests

from . import config as C

S = requests.Session()
S.headers["User-Agent"] = C.USER_AGENT


def _get(url, params=None, tries=3, timeout=30):
    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (422, 429, 500, 502, 503):
                # Arctic Shift says how long to back off; respect it (capped so a run can't stall)
                wait = r.headers.get("x-ratelimit-reset")
                time.sleep(min(int(wait) + 1, 30) if wait and wait.isdigit() and r.status_code != 500 else 3 * (i + 1))
                continue
            return None
        except requests.RequestException:
            time.sleep(3 * (i + 1))
    return None


def fetch_items(kind, sub, after, before):
    """All comments/posts in [after, before) for one subreddit, oldest first."""
    fields = "id,created_utc,author,body" if kind == "comments" else "id,created_utc,author,title,selftext"
    out, cur = [], int(after)
    for _ in range(C.MAX_PAGES_PER_SUB):
        j = _get(f"{C.ARCTIC}/api/{kind}/search",
                 {"subreddit": sub, "after": cur, "before": int(before), "limit": 100, "sort": "asc", "fields": fields})
        data = (j or {}).get("data") or []
        if not data:
            break
        out.extend(data)
        last = max(int(d["created_utc"]) for d in data)
        if len(data) < 100 or last <= cur:
            break
        cur = last  # items sharing this second may repeat; callers dedupe by id
        time.sleep(0.4)
    return out


def posts_title_history(ticker, sub, days=14):
    """Hourly counts of post titles mentioning the ticker (cheap baseline bootstrap)."""
    now = int(time.time())
    j = _get(f"{C.ARCTIC}/api/posts/search/aggregate",
             {"aggregate": "created_utc", "frequency": "hour", "subreddit": sub, "title": ticker,
              "after": now - days * 86400, "before": now})
    return [(d["created_utc"], int(d["count"])) for d in (j or {}).get("data") or []]


def price_context(ticker):
    """Last price, 24h move and relative volume from Yahoo 60m bars (incl. pre/post market)."""
    j = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
             {"range": "10d", "interval": "60m", "includePrePost": "true"})
    try:
        res = j["chart"]["result"][0]
        ts = res["timestamp"]
        q = res["indicators"]["quote"][0]
        rows = [(t, c, v or 0) for t, c, v in zip(ts, q["close"], q["volume"]) if c is not None]
        t_last, p_last, _ = rows[-1]
        ref = next((c for t, c, _ in reversed(rows) if t <= t_last - 86400), rows[0][1])
        vol24 = sum(v for t, _, v in rows if t > t_last - 86400)
        before = [(t, v) for t, _, v in rows if t <= t_last - 86400]
        days = max(1, (t_last - 86400 - rows[0][0]) / 86400)
        vol_avg = sum(v for _, v in before) / days if before else 0
        meta = res.get("meta", {})
        return {"price": p_last, "move_24h": p_last / ref - 1 if ref else 0.0,
                "rel_volume": vol24 / vol_avg if vol_avg else None,
                "name": meta.get("longName") or meta.get("shortName") or ticker, "ok": True,
                "etf": (meta.get("instrumentType") or "").upper() in ("ETF", "MUTUALFUND", "INDEX"),
                "dollar_vol_m": round(vol_avg * p_last / 1e6, 1) if vol_avg else None,
                "last_ts": t_last, "live": time.time() - t_last < 2 * 3600}
    except (TypeError, KeyError, IndexError, ZeroDivisionError):
        return {"ok": False}


def load_universe():
    """US-listed tickers from Nasdaq Trader symbol files (NASDAQ + NYSE/other)."""
    syms = set()
    for url, col in [("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", 0),
                     ("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt", 0)]:
        try:
            r = S.get(url, timeout=30)
            for line in r.text.splitlines()[1:]:
                parts = line.split("|")
                if len(parts) > 3 and parts[col].isalpha() and "File Creation" not in line:
                    syms.add(parts[col].upper())
        except requests.RequestException:
            pass
    return sorted(syms)


# ---------------------------------------------------------------- Stocktwits
ST = "https://api.stocktwits.com/api/2"
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/126.0 Safari/537.36", "Accept": "application/json, text/plain, */*"}


def _iso(ts):
    import datetime as dt
    return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()


def stocktwits_trending():
    """[{ticker, rank, score, mcap_musd, float_m, summary}] or None if blocked."""
    try:
        r = S.get(f"{ST}/trending/symbols.json", headers=BROWSER_UA, timeout=20)
        if r.status_code != 200:
            return None
        out = []
        for i, s in enumerate(r.json().get("symbols", [])):
            f = s.get("fundamentals") or {}
            def num(k):
                try:
                    return float(str(f.get(k)).replace(",", ""))
                except (TypeError, ValueError):
                    return None
            out.append({"ticker": s.get("symbol", "").upper(), "rank": s.get("rank") or i + 1,
                        "score": s.get("trending_score"), "mcap_musd": num("MarketCap"),
                        "float_m": num("FloatCurrent"), "shares_m": num("SharesOutstanding"),
                        "summary": (s.get("trends") or {}).get("summary") or "",
                        "cls": s.get("instrument_class")})
        return out
    except (requests.RequestException, ValueError):
        return None


def stocktwits_stream(ticker, now=None):
    """Messages in the last hour (of the latest 30), bullish share, and implied hourly rate."""
    now = now or time.time()
    try:
        r = S.get(f"{ST}/streams/symbol/{ticker}.json", headers=BROWSER_UA, timeout=20)
        if r.status_code != 200:
            return None
        msgs = r.json().get("messages", [])
    except (requests.RequestException, ValueError):
        return None
    if not msgs:
        return {"n_1h": 0, "rate_h": 0.0, "bull": None, "texts": []}
    try:
        ts = [_iso(m["created_at"]) for m in msgs]
    except (KeyError, ValueError, TypeError):
        return None
    n1 = sum(1 for t in ts if t >= now - 3600)
    span_h = max((now - min(ts)) / 3600, 1 / 60)
    sents = [((m.get("entities") or {}).get("sentiment") or {}).get("basic") for m in msgs]
    tagged = [s for s in sents if s]
    bull = sum(1 for s in tagged if s == "Bullish") / len(tagged) if tagged else None
    return {"n_1h": n1, "rate_h": len(msgs) / span_h, "bull": bull, "saturated": n1 >= len(msgs) == 30,
            "texts": [m.get("body", "")[:400] for m in msgs[:30]]}


# ---------------------------------------------------------------- short interest (FINRA)
def short_interest(ticker):
    """Latest FINRA short interest: shares short, days to cover, change %, settlement date."""
    import datetime as dt
    start = (dt.date.today() - dt.timedelta(days=60)).isoformat()
    try:
        r = S.post("https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest",
                   headers={"Accept": "application/json", "Content-Type": "application/json"}, timeout=20,
                   json={"limit": 10, "compareFilters": [{"compareType": "equal", "fieldName": "symbolCode", "fieldValue": ticker}],
                         "dateRangeFilters": [{"fieldName": "settlementDate", "startDate": start, "endDate": dt.date.today().isoformat()}]})
        rows = r.json() if r.status_code == 200 else []
        if not rows:
            return None
        x = max(rows, key=lambda q: q["settlementDate"])
        return {"short_shares": x.get("currentShortPositionQuantity"), "dtc": x.get("daysToCoverQuantity"),
                "chg_pct": x.get("changePercent"), "date": x.get("settlementDate")}
    except (requests.RequestException, ValueError, KeyError):
        return None


# ---------------------------------------------------------------- Nasdaq (options + shares)
NQ = "https://api.nasdaq.com/api/quote"


def _nqnum(v):
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return 0.0


def shares_outstanding(ticker):
    try:
        r = S.get(f"{NQ}/{ticker}/summary", params={"assetclass": "stocks"}, headers=BROWSER_UA, timeout=20)
        d = r.json()["data"]["summaryData"]
        mc, pc = _nqnum(d["MarketCap"]["value"]), _nqnum(d["PreviousClose"]["value"])
        return mc / pc if pc else None
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def options_activity(ticker, expiries=2):
    """Call/put volume and call volume vs open interest over the nearest expiries (today's session)."""
    try:
        r = S.get(f"{NQ}/{ticker}/option-chain", headers=BROWSER_UA, timeout=25,
                  params={"assetclass": "stocks", "limit": 400, "fromdate": "all", "excode": "oprac",
                          "callput": "callput", "money": "all", "type": "all"})
        rows = r.json()["data"]["table"]["rows"]
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None
    if not rows:            # stock with no listed options: Nasdaq returns rows = null
        return {"call_vol": 0, "put_vol": 0, "cp_ratio": None, "call_vol_oi": None}
    groups, cv, pv, coi = 0, 0.0, 0.0, 0.0
    for row in rows:
        if row.get("expirygroup"):
            groups += 1
            if groups > expiries:
                break
            continue
        cv += _nqnum(row.get("c_Volume"))
        pv += _nqnum(row.get("p_Volume"))
        coi += _nqnum(row.get("c_Openinterest"))
    if cv + pv == 0:
        return {"call_vol": 0, "put_vol": 0, "cp_ratio": None, "call_vol_oi": None}
    return {"call_vol": int(cv), "put_vol": int(pv), "cp_ratio": cv / pv if pv else None,
            "call_vol_oi": cv / coi if coi else None}


# ---------------------------------------------------------------- price bars (journal + charts)
def price_bars(ticker, rng="1mo", interval="60m"):
    """[(ts, open, high, low, close)] incl. pre/post market, oldest first. [] on failure."""
    j = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
             {"range": rng, "interval": interval, "includePrePost": "true"})
    try:
        res = j["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        return [(t, o, h, l, c) for t, o, h, l, c in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"])
                if None not in (o, h, l, c)]
    except (TypeError, KeyError, IndexError):
        return []


# ---------------------------------------------------------------- earnings calendar (Nasdaq)
def earnings_on(date_iso):
    """Set of tickers reporting earnings on a date (YYYY-MM-DD), or None on failure."""
    try:
        r = S.get(f"https://api.nasdaq.com/api/calendar/earnings", params={"date": date_iso},
                  headers=BROWSER_UA, timeout=20)
        rows = (r.json().get("data") or {}).get("rows") or []
        return {row["symbol"].upper() for row in rows if row.get("symbol")}
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        return None


# ---------------------------------------------------------------- Google Trends (unofficial, best effort)
GT = "https://trends.google.com"


def _gt_json(text):
    return __import__("json").loads(text[text.index("\n") + 1:])


def google_trends(ticker):
    """Hourly US search interest for '<TICKER> stock' over 7 days.

    Returns {"ratio": last-6h mean / earlier mean, "last": latest value, "series": [...]} or None.
    Google often answers 429 to cloud servers; callers must treat None as 'unknown'.
    """
    import json
    sess = requests.Session()
    sess.headers.update(BROWSER_UA)
    try:
        sess.get(f"{GT}/?geo=US", timeout=15)  # sets the NID cookie
        req = {"comparisonItem": [{"keyword": f"{ticker} stock", "geo": "US", "time": "now 7-d"}],
               "category": 0, "property": ""}
        r = sess.get(f"{GT}/trends/api/explore", params={"hl": "en-US", "tz": 0, "req": json.dumps(req)}, timeout=20)
        if r.status_code != 200:
            return None
        w = next(x for x in _gt_json(r.text)["widgets"] if x.get("id") == "TIMESERIES")
        r2 = sess.get(f"{GT}/trends/api/widgetdata/multiline",
                      params={"hl": "en-US", "tz": 0, "req": json.dumps(w["request"]), "token": w["token"]}, timeout=20)
        if r2.status_code != 200:
            return None
        tl = _gt_json(r2.text)["default"]["timelineData"]
    except (requests.RequestException, ValueError, KeyError, StopIteration):
        return None
    vals = [(int(p["time"]), p["value"][0]) for p in tl if (p.get("hasData") or [True])[0]]
    if len(vals) < 30:
        return None
    recent = [v for _, v in vals[-6:]]
    earlier = [v for _, v in vals[:-24]]
    base = sum(earlier) / len(earlier) if earlier else 0
    now_avg = sum(recent) / len(recent)
    return {"ratio": round(now_avg / max(base, 1), 1), "last": vals[-1][1], "series": vals[-72:]}
