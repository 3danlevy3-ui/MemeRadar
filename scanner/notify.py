"""Telegram alerts (Hebrew)."""
import html

import requests

from . import config as C

e = html.escape
HIST = ("בבקטסט (2024–2026): בערך 1 מכל 5 התראות הגיע ל-+20% תוך 3 ימים, אבל בערך 1 מכל 4 ירד 15%. "
        "כשימי הכיסוי של השורט היו 4 ומעלה, הסיכוי לנפילה ירד מ-34% ל-11%. זה אות לתנודתיות, לא אות קנייה.")


def send(text):
    if not (C.TELEGRAM_TOKEN and C.TELEGRAM_CHAT_ID):
        print("[telegram disabled]\n" + text)
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{C.TELEGRAM_TOKEN}/sendMessage",
                          json={"chat_id": C.TELEGRAM_CHAT_ID, "text": text[:4000], "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=20)
        if not r.ok:
            print("telegram error", r.status_code, r.text[:200])
        return r.ok
    except requests.RequestException as ex:
        print("telegram error", ex)
        return False


def _pct(v):
    return f"{v * 100:.0f}%" if v is not None else "?"


def fmt_alert(c, llm=None):
    icon = "🟢" if c["tier"] == "EARLY" else "🟠"
    tier = "מוקדם: המחיר עוד לא זז" if c["tier"] == "EARLY" else "מומנטום: המחיר כבר בתנועה"
    src = " + ".join(c.get("sources") or []) or "?"
    L = [f"{icon} <b>${e(c['ticker'])}</b> · ציון {c['score']}/100 · {tier}", f"מקורות: <b>{e(src)}</b>"]
    if c.get("name"):
        L.append(e(c["name"]))
    if c.get("mentions_1h"):
        L.append(f"Reddit: {c['mentions_1h']} אזכורים בשעה (פי {c.get('burst', '?')} מהרגיל), "
                 f"{c.get('authors_1h', '?')} כותבים שונים")
    if c.get("st_1h") is not None:
        rank = f", מקום {c['st_rank']} בטרנדינג" if c.get("st_rank") else ""
        L.append(f"Stocktwits: {c['st_1h']} הודעות בשעה (פי {c.get('st_burst', '?')}{rank}), "
                 f"{_pct(c.get('st_bull'))} בולישיות")
    if c.get("x_1h") is not None:
        L.append(f"X: {c['x_1h']} פוסטים בשעה (פי {c.get('x_burst', '?')}), {c.get('x_24h', '?')} ב-24 שעות")
    if c.get("influencer"):
        L.append(f"⭐ פוסט חדש של @{e(c['influencer'])}")
    if c.get("price") is not None:
        rv = f" · מחזור פי {c['rel_volume']}" if c.get("rel_volume") else ""
        L.append(f"מחיר: {c['price']} · 24 שעות: {c['move_24h']:+.1f}%{rv}")
    else:
        L.append("מחיר: לא זמין (בדוק ידנית אם כבר זז)")
    si, opt = c.get("si") or {}, c.get("options") or {}
    fuel = []
    if si.get("dtc") is not None:
        pct = f", {si['pct_out']}% מהמניות" if si.get("pct_out") is not None else ""
        fuel.append(f"שורט: {si['dtc']:.1f} ימים לכיסוי{pct}")
    if opt.get("cp_ratio"):
        fuel.append(f"אופציות היום: קול/פוט {opt['cp_ratio']:.1f}")
    if fuel:
        L.append("⛽ " + " · ".join(fuel))
    if llm:
        tags = [t for t, k in (("שיח על סקוויז", "squeeze_talk"), ("⚠️ חשד לפאמפ/בוטים", "pump_suspect")) if llm.get(k)]
        L.append(f"סנטימנט: {llm.get('sentiment', '?')} · הייפ: {llm.get('hype', '?')}/10" + (f" · {' · '.join(tags)}" if tags else ""))
        if llm.get("summary_he"):
            L.append("🗣 " + e(llm["summary_he"]))
    elif c.get("st_summary"):
        L.append("🗣 " + e(c["st_summary"][:300]))
    t = e(c["ticker"])
    L.append(f"<a href='https://www.reddit.com/r/wallstreetbets/search/?q=%24{t}&sort=new'>Reddit</a> · "
             f"<a href='https://stocktwits.com/symbol/{t}'>Stocktwits</a> · "
             f"<a href='https://x.com/search?q=%24{t}&f=live'>X</a>")
    L.append(f"<i>{HIST}</i>")
    return "\n".join(L)


def fmt_influencer(acct, post, tickers):
    tk = " ".join(f"${e(t)}" for t in sorted(tickers)) or "(בלי סימול מזוהה)"
    return (f"⭐ <b>@{e(acct)} פרסם עכשיו</b> {tk}\n{e(post.get('text', '')[:500])}\n"
            f"<a href='https://x.com/{e(acct)}/status/{e(post.get('id', ''))}'>לפוסט</a>")


def fmt_exit(x):
    r = f"{x['ret'] * 100:+.1f}%" if x.get("ret") is not None else "?"
    return (f"🔴 <b>יציאה? ${e(x['ticker'])}</b>\nסיבה: {e(x['reason'])}\n"
            f"שינוי מאז ההתראה: {r}")


def fmt_health(src, xstate, open_alerts):
    lines = ["🩺 <b>MemeRadar – סטטוס יומי</b>"]
    for name, (ok, bad) in sorted(src.items()):
        mark = "✅" if bad == 0 else ("⚠️" if ok else "❌")
        lines.append(f"{mark} {e(name)}: {ok} הצלחות, {bad} כשלונות")
    if xstate.get("spent") is not None and xstate.get("day"):
        lines.append(f"X: הוצאה היום ${xstate['spent']:.2f} מתוך ${C.X_DAILY_BUDGET:.2f}")
    lines.append(f"התראות פתוחות: {open_alerts}")
    return "\n".join(lines)
