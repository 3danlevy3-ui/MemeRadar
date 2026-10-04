"""PNG charts for Telegram (matplotlib). Labels are English: matplotlib can't shape Hebrew."""
import io
import time

SIG, WARM, INK, MUTED, GRID = "#00876a", "#b86e2a", "#18201d", "#78837e", "#e6e9e7"


def _plt():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        return plt, mdates
    except Exception:
        return None, None


def _style(ax):
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)


def alert_chart(ticker, mentions, bars, trends=None, alert_ts=None):
    """mentions: [(ts, count)] hourly; bars: [(ts,o,h,l,c)]; trends: [(ts, 0-100)]. Returns PNG bytes or None."""
    plt, mdates = _plt()
    if not plt or (not mentions and not bars):
        return None
    import datetime as dt
    tz = dt.timezone(dt.timedelta(hours=3))
    D = lambda ts: dt.datetime.fromtimestamp(ts, tz)
    rows = 3 if trends else 2
    fig, axes = plt.subplots(rows, 1, figsize=(7, 1.9 * rows + 0.6), sharex=True,
                             gridspec_kw={"height_ratios": [1] * rows})
    fig.patch.set_facecolor("white")
    ax = axes[0]
    if mentions:
        ax.bar([D(t) for t, _ in mentions], [v for _, v in mentions], width=1 / 26, color=SIG)
    ax.set_title(f"${ticker}  ·  Reddit mentions / hour", loc="left", fontsize=10, color=INK)
    _style(ax)
    ax = axes[1]
    if bars:
        ax.plot([D(b[0]) for b in bars], [b[4] for b in bars], color=INK, linewidth=1.6)
        ax.scatter([D(bars[-1][0])], [bars[-1][4]], color=INK, s=14, zorder=3)
        ax.annotate(f"${bars[-1][4]:.2f}", (D(bars[-1][0]), bars[-1][4]), textcoords="offset points",
                    xytext=(4, 4), fontsize=8, color=INK)
    ax.set_title("Price (incl. pre/after-market)", loc="left", fontsize=10, color=INK)
    _style(ax)
    if trends:
        ax = axes[2]
        ax.fill_between([D(t) for t, _ in trends], [v for _, v in trends], color=WARM, alpha=0.25, linewidth=0)
        ax.plot([D(t) for t, _ in trends], [v for _, v in trends], color=WARM, linewidth=1.4)
        ax.set_title("Google searches (0-100)", loc="left", fontsize=10, color=INK)
        _style(ax)
    if alert_ts:
        for a in axes:
            a.axvline(D(alert_ts), color=WARM, linestyle="--", linewidth=1)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d.%m %H:%M", tz=tz))
    fig.autofmt_xdate(rotation=0, ha="center")
    fig.text(0.99, 0.005, "Israel time · MemeRadar", ha="right", fontsize=7, color=MUTED)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    return buf.getvalue()


def weekly_chart(entries, groups):
    """Left: cumulative paper P&L of the experiment rules. Right: +20%-in-3-days rate per source."""
    plt, mdates = _plt()
    if not plt:
        return None
    import datetime as dt
    done = sorted([e for e in entries if "sim" in e["out"]], key=lambda e: e["t"])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 3.6), gridspec_kw={"width_ratios": [1.5, 1]})
    fig.patch.set_facecolor("white")
    if done:
        cum, s = [], 0.0
        for e in done:
            s += e["out"]["sim"] * 100
            cum.append(s)
        xs = [dt.datetime.utcfromtimestamp(e["t"]) for e in done]
        a1.plot(xs, cum, color=SIG, linewidth=2)
        a1.fill_between(xs, cum, 0, color=SIG, alpha=0.12, linewidth=0)
        a1.axhline(0, color=MUTED, linewidth=0.8)
        a1.annotate(f"{cum[-1]:+.1f}%", (xs[-1], cum[-1]), textcoords="offset points", xytext=(4, 0),
                    fontsize=9, color=INK)
        a1.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    else:
        a1.text(0.5, 0.5, "No completed alerts yet", ha="center", va="center", color=MUTED, transform=a1.transAxes)
    a1.set_title("Paper P&L, sum of % per alert", loc="left", fontsize=10, color=INK)
    _style(a1)
    src = [(k.replace("מקור: ", ""), v) for k, v in groups.items() if k.startswith("מקור: ") and v["hit20"] is not None]
    if src:
        names = [n for n, _ in src]
        a2.barh(names, [v["hit20"] for _, v in src], color=SIG, height=0.55)
        for i, (_, v) in enumerate(src):
            a2.text(v["hit20"] + 1, i, f"{v['hit20']}%  (n={v['evaluated']})", va="center", fontsize=8, color=INK)
        a2.set_xlim(0, 100)
    else:
        a2.text(0.5, 0.5, "Not enough data", ha="center", va="center", color=MUTED, transform=a2.transAxes)
    a2.set_title("Hit +20% within 3 days, by source", loc="left", fontsize=10, color=INK)
    _style(a2)
    a2.grid(axis="x", color=GRID)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    return buf.getvalue()


def hourly_mentions(state, ticker, now, hours=48):
    out = []
    for i in range(hours, 0, -1):
        ts = now - i * 3600
        k = time.strftime("%Y%m%d%H", time.gmtime(ts))
        out.append((ts - ts % 3600, state["hours"].get(k, {"T": {}})["T"].get(ticker, 0)))
    return out
