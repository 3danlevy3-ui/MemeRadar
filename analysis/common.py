"""Shared loaders for MemeRadar research data."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"


def _series(pairs):
    if not pairs:
        return pd.Series(dtype=float)
    s = pd.Series({pd.Timestamp(t, unit="s"): c for t, c in pairs}).sort_index()
    return s[~s.index.duplicated()].astype(float)


def load_mentions():
    """Return dict key -> hourly Series. key = 'posts:TICKER' / 'comments:TICKER'.

    Arctic Shift buckets are labelled by the START of the hour, so a count in
    bucket 13:00 is only known at 14:00 (we shift by +1h wherever we act on it).
    """
    out = {}
    for f in ["posts_hourly_2425.json", "events.json"]:
        p = DATA / f
        if not p.exists():
            continue
        R = json.load(open(p))["R"]
        for k, v in R.items():
            s = _series(v)
            out[k] = s if k not in out else pd.concat([out[k], s]).groupby(level=0).max()
    return out


def load_prices():
    P = json.load(open(DATA / "prices.json"))
    daily, hourly = {}, {}
    for t, d in P["daily"].items():
        if "err" in d:
            continue
        df = pd.DataFrame({k: d[k] for k in "ohlcv"}, index=pd.to_datetime(d["t"], unit="s").normalize())
        daily[t] = df.dropna(subset=["c"])
    for t, d in P["hourly"].items():
        if "err" in d:
            continue
        df = pd.DataFrame({k: d[k] for k in "ohlcv"}, index=pd.to_datetime(d["t"], unit="s"))
        hourly[t] = df.dropna(subset=["c"])
    return daily, hourly


def price_events(daily, ret_thr=0.25, high_thr=0.40, vol_mult=3.0, gap_days=15):
    rows = []
    for t, df in daily.items():
        df = df.copy()
        df["pc"] = df.c.shift(1)
        df["ret"] = df.c / df.pc - 1
        df["hret"] = df.h / df.pc - 1
        df["vrel"] = df.v / df.v.rolling(20).mean().shift(1)
        ev = df[((df.ret > ret_thr) | (df.hret > high_thr)) & (df.vrel > vol_mult)]
        last = None
        for d, r in ev.iterrows():
            if last is not None and (d - last).days < gap_days:
                continue
            last = d
            rows.append(dict(tk=t, date=d, ret=r.ret, hret=r.hret, vrel=r.vrel, prev_close=r.pc))
    return pd.DataFrame(rows)
