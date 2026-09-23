"""MemeRadar research backtest.

Three studies:
  A. Classic events (daily): did WSB chatter rise before the first big price day?
  B. Hourly lead (2024-26 events, WSB comments): how many hours before price
     ignition did mentions cross an alert threshold, and had price already moved?
  C. Continuous walk-forward (2024-09..2026-09, WSB post titles, 18 tickers):
     every alert the rule would have fired, and what the stock did next.

No look-ahead: a mention bucket [h, h+1) is only used at h+1; entries are at the
open of the first price bar starting at/after the alert time.
"""
import json
import sys

import numpy as np
import pandas as pd

from common import DATA, load_mentions, load_prices, price_events

M = load_mentions()
D, H = load_prices()
OUT = {}


# ---------------------------------------------------------------- helpers
def alert_rule(counts, baseline_mu, mult=5.0, min_count=5, z=4.0):
    """Burst rule on hourly counts vs baseline mean (Poisson-style)."""
    mu = np.maximum(baseline_mu, 0.2)
    thr = np.maximum.reduce([mu * mult, mu + z * np.sqrt(mu), np.full_like(mu, min_count, dtype=float)])
    return counts >= thr, thr


def entry_after(hdf, t):
    after = hdf[hdf.index >= t]
    return (after.index[0], after.o.iloc[0]) if len(after) else (None, None)


def ref_price(hdf, t, hours=24):
    before = hdf[hdf.index <= t - pd.Timedelta(hours=hours)]
    return before.c.iloc[-1] if len(before) else np.nan


def ignition(hdf, start, end, thr=0.10):
    """First bar whose close is >= thr above the close 24h earlier."""
    w = hdf[start:end]
    for ts, row in w.iterrows():
        rp = ref_price(hdf, ts, 24)
        if rp and row.c >= rp * (1 + thr):
            return ts, rp
    return None, None


# ------------------------------------------------------------- Study A
def study_a():
    rows = []
    classic = [("GME", "2021-01-13"), ("GME", "2021-01-22"), ("AMC", "2021-01-26"), ("KOSS", "2021-01-26"),
               ("NOK", "2021-01-27"), ("BB", "2021-01-13"), ("AMC", "2021-05-26"), ("AMC", "2021-06-02"),
               ("CLOV", "2021-06-08"), ("WKHS", "2021-06-03"), ("BB", "2021-06-02"), ("KOSS", "2021-06-02"),
               ("BBBY", "2022-08-05"), ("GME", "2024-05-13"), ("AMC", "2024-05-13"), ("KOSS", "2024-05-13")]
    for tk, day in classic:
        k = "comments:" + tk
        if k not in M:
            continue
        s = M[k].resample("D").sum()
        s = s.where(s > 0)  # a whole day at 0 = archive gap / failed fetch, not silence
        d = pd.Timestamp(day)
        base = s[d - pd.Timedelta(days=21): d - pd.Timedelta(days=4)]
        base = base[base > 0]
        if len(base) < 5:
            continue
        mu = base.median()
        r = {"ticker": tk, "onset": day, "baseline_per_day": int(mu)}
        for off in [-3, -2, -1, 0]:
            v = s.get(d + pd.Timedelta(days=off), np.nan)
            r[f"D{off:+d}"] = round(v / mu, 1) if mu else np.nan
        if tk in D:
            px = D[tk].c
            p0 = px[:d - pd.Timedelta(days=1)]
            r["price_D-1_vs_D-4_%"] = round((p0.iloc[-1] / p0.iloc[-4] - 1) * 100) if len(p0) > 4 else np.nan
            p1 = px[d:d + pd.Timedelta(days=10)]
            r["max_next10d_%"] = round((p1.max() / p0.iloc[-1] - 1) * 100) if len(p1) else np.nan
        rows.append(r)
    df = pd.DataFrame(rows)
    OUT["A"] = df.to_dict("records")
    return df


# ------------------------------------------------------------- Study B
EV2 = [("KSS", "2025-07-22"), ("GPRO", "2025-07-22"), ("DNUT", "2025-07-22"), ("BYND", "2025-10-17"),
       ("AMC", "2026-07-20"), ("QUBT", "2024-11-13"), ("RGTI", "2024-11-25"), ("WKHS", "2025-07-08"),
       ("AEO", "2025-09-04"), ("KSS", "2025-11-25"), ("BYND", "2026-04-20"), ("GPRO", "2026-08-31"),
       ("SPCE", "2025-05-16"), ("TLRY", "2025-09-29")]


def study_b(mult=5.0, min_count=5, z=4.0):
    rows = []
    for tk, day in EV2:
        k = "comments:" + tk
        if k not in M or tk not in H:
            continue
        s = M[k]
        d = pd.Timestamp(day)
        ctrl = s[d - pd.Timedelta(days=40): d - pd.Timedelta(days=34)]
        full = pd.Series(0.0, index=pd.date_range(d - pd.Timedelta(days=5), d + pd.Timedelta(hours=23), freq="h"))
        win = s.reindex(full.index).fillna(0)
        # baseline: control window mean, same hour-of-day profile would be nicer but data is thin
        mu = ctrl.reindex(pd.date_range(ctrl.index.min() if len(ctrl) else d, periods=144, freq="h")).fillna(0).mean() if len(ctrl) else 0.5
        fired, thr = alert_rule(win.values, np.full(len(win), mu), mult, min_count, z)
        hdf = H[tk]
        ign, rp = ignition(hdf, d - pd.Timedelta(days=5), d + pd.Timedelta(hours=23))
        first_alert = None
        if fired.any():
            first_alert = win.index[np.argmax(fired)] + pd.Timedelta(hours=1)  # known at end of bucket
        r = dict(ticker=tk, onset=day, baseline_per_hr=round(mu, 2),
                 ignition=str(ign) if ign is not None else None,
                 first_alert=str(first_alert) if first_alert is not None else None)
        if ign is not None and first_alert is not None:
            lead = (ign - first_alert).total_seconds() / 3600
            r["lead_hours"] = round(lead, 1)
            ref = ref_price(hdf, first_alert, 24)
            at = hdf[:first_alert].c.iloc[-1] if len(hdf[:first_alert]) else np.nan
            r["price_move_before_alert_%"] = round((at / ref - 1) * 100, 1) if ref else None
            et, ep = entry_after(hdf, first_alert)
            nxt = hdf[et: et + pd.Timedelta(days=3)] if et is not None else None
            if nxt is not None and len(nxt):
                r["entry"] = round(ep, 2)
                r["max_3d_%"] = round((nxt.h.max() / ep - 1) * 100, 1)
                r["min_3d_%"] = round((nxt.l.min() / ep - 1) * 100, 1)
        r["mentions_24h_before_ign"] = int(win[: ign - pd.Timedelta(hours=1)].tail(24).sum()) if ign is not None else None
        r["peak_hr_mentions"] = int(win.max())
        rows.append(r)
    df = pd.DataFrame(rows)
    OUT["B"] = df.to_dict("records")
    return df


# ------------------------------------------------------------- Study C
CONT = ["KSS", "GPRO", "DNUT", "BYND", "WKHS", "QUBT", "RGTI", "SPCE", "TLRY", "AMC", "GME", "CENN",
        "LUNR", "SOUN", "HIMS", "AEO", "KOSS", "ASTS"]
START, END = pd.Timestamp("2024-10-10"), pd.Timestamp("2026-09-18")


def study_c(win_h=6, mult=4.0, min_posts=4, max_prior_move=0.10, cooldown_h=72, use_share=True):
    allp = M["posts:__ALL__"].reindex(pd.date_range(START - pd.Timedelta(days=30), END, freq="h")).fillna(0)
    alerts = []
    for tk in CONT:
        k = "posts:" + tk
        if k not in M or tk not in H:
            continue
        s = M[k].reindex(allp.index).fillna(0)
        roll = s.rolling(win_h).sum()
        # baseline: mean 6h-window count over prior 14 days, excluding the current window
        base = s.shift(win_h).rolling(24 * 14, min_periods=24 * 7).mean() * win_h
        if use_share:
            share_now = roll / allp.rolling(win_h).sum().replace(0, np.nan)
            share_base = (s.shift(win_h).rolling(24 * 14).sum() / allp.shift(win_h).rolling(24 * 14).sum().replace(0, np.nan))
            cond_share = share_now >= mult * share_base.clip(lower=1e-5)
        else:
            cond_share = True
        cond = (roll >= min_posts) & (roll >= mult * base.clip(lower=0.25)) & cond_share
        hdf = H[tk]
        last = None
        for ts in roll.index[cond.fillna(False).values]:
            if ts < START or ts > END:
                continue
            t_known = ts + pd.Timedelta(hours=1)
            if last is not None and (t_known - last).total_seconds() < cooldown_h * 3600:
                continue
            ref = ref_price(hdf, t_known, 24)
            now = hdf[:t_known]
            if not len(now) or not ref:
                continue
            prior = now.c.iloc[-1] / ref - 1
            et, ep = entry_after(hdf, t_known)
            if et is None or (et - t_known).days > 4:
                continue
            last = t_known
            fw = hdf[et: et + pd.Timedelta(days=3)]
            fw1 = hdf[et: et + pd.Timedelta(days=1)]
            fw10 = hdf[et: et + pd.Timedelta(days=10)]
            alerts.append(dict(ticker=tk, alert=t_known, entry_time=et, entry=ep, prior_24h=prior,
                               posts_6h=int(roll[ts]), base_6h=float(base[ts]) if not np.isnan(base[ts]) else None,
                               max_1d=fw1.h.max() / ep - 1, max_3d=fw.h.max() / ep - 1, min_3d=fw.l.min() / ep - 1,
                               ret_1d=fw1.c.iloc[-1] / ep - 1, ret_3d=fw.c.iloc[-1] / ep - 1,
                               ret_10d=fw10.c.iloc[-1] / ep - 1))
    A = pd.DataFrame(alerts)
    # unconditional base rate: every trading-hour bar for the same tickers
    base_rows = []
    for tk in CONT:
        if tk not in H:
            continue
        hdf = H[tk][START:END]
        idx = hdf.index[::7]  # thin sample
        for et in idx:
            ep = hdf.o[et]
            fw = hdf[et: et + pd.Timedelta(days=3)]
            if len(fw) < 5 or not ep:
                continue
            base_rows.append(dict(max_3d=fw.h.max() / ep - 1, ret_3d=fw.c.iloc[-1] / ep - 1, min_3d=fw.l.min() / ep - 1))
    B = pd.DataFrame(base_rows)
    return A, B


def summarize(A, B, label):
    def stats(df):
        return dict(n=len(df), hit20_3d=round((df.max_3d >= 0.20).mean() * 100, 1),
                    hit10_3d=round((df.max_3d >= 0.10).mean() * 100, 1),
                    med_ret_3d=round(df.ret_3d.median() * 100, 1), mean_ret_3d=round(df.ret_3d.mean() * 100, 1),
                    dd15_3d=round((df.min_3d <= -0.15).mean() * 100, 1))
    early = A[A.prior_24h < 0.10]
    late = A[A.prior_24h >= 0.10]
    res = {"label": label, "all_alerts": stats(A) if len(A) else None,
           "early_alerts(price<+10%)": stats(early) if len(early) else None,
           "late_alerts(price>=+10%)": stats(late) if len(late) else None,
           "random_baseline": stats(B)}
    return res


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    a = study_a()
    print("\n=== Study A: classic events, mentions as multiple of baseline (daily) ===")
    print(a.to_string(index=False))
    b = study_b()
    print("\n=== Study B: hourly lead, WSB comments (2024-26) ===")
    print(b.to_string(index=False))
    A, B = study_c()
    A.to_csv(DATA / "study_c_alerts.csv", index=False)
    print("\n=== Study C: continuous walk-forward, WSB post-title bursts ===")
    s = summarize(A, B, "default")
    OUT["C"] = s
    print(json.dumps(s, indent=1))
    json.dump(OUT, open(DATA / "results.json", "w"), default=str, indent=1)


def simulate(A, tp=0.20, sl=0.10, max_days=3, cost=0.005):
    """Enter at alert entry price; exit at +tp / -sl / time. Stop assumed first if both hit in one bar."""
    res = []
    for _, r in A.iterrows():
        hdf = H[r.ticker]
        fw = hdf[r.entry_time: r.entry_time + pd.Timedelta(days=max_days)]
        ep = r.entry
        out = None
        for _, b in fw.iterrows():
            if b.l <= ep * (1 - sl):
                out = -sl; break
            if b.h >= ep * (1 + tp):
                out = tp; break
        if out is None:
            out = fw.c.iloc[-1] / ep - 1
        res.append(out - cost)
    return pd.Series(res, index=A.index)


def grid():
    rows = []
    for mult in [3, 4, 6, 8]:
        for mp in [3, 4, 6, 10]:
            A, B = study_c(mult=mult, min_posts=mp)
            if len(A) < 10:
                continue
            e = A[A.prior_24h < 0.10]
            t = simulate(e) if len(e) else pd.Series(dtype=float)
            rows.append(dict(mult=mult, min_posts=mp, n=len(A), n_early=len(e),
                             hit20_early=round((e.max_3d >= .2).mean() * 100, 1) if len(e) else None,
                             trade_mean_early=round(t.mean() * 100, 2) if len(t) else None,
                             trade_win_early=round((t > 0).mean() * 100, 1) if len(t) else None))
    return pd.DataFrame(rows)
