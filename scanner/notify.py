"""Telegram alerts (Hebrew)."""
import html

import requests

from . import config as C

e = html.escape
HIST = ("בבקטסט (2024–2026): בערך 1 מכל 5 התראות הגיע ל-+20% תוך 3 ימים, אבל בערך 1 מכל 4 ירד 15%. "
        "כשימי הכיסוי של השורט היו 4 ומעלה, הסיכוי לנפילה ירד מ-34% ל-11%. זה אות לתנודתיות, לא אות קנייה.")


API = "https://api.telegram.org/bot{}/{}"


def _tg(method, data=None, files=None):
    if not (C.TELEGRAM_TOKEN and C.TELEGRAM_CHAT_ID):
        return None
    try:
        r = requests.post(API.format(C.TELEGRAM_TOKEN, method), data=data if files else None,
                          json=None if files else data, files=files, timeout=30)
        j = r.json()
        if not j.get("ok"):
            print("telegram", method, j.get("description"))
            return None
        return j.get("result")
    except (requests.RequestException, ValueError) as ex:
        print("telegram error", ex)
        return None


def send(text, buttons=None):
    """Send HTML text. buttons: [[(label, callback_data), ...], ...]. Returns message_id or None."""
    if not (C.TELEGRAM_TOKEN and C.TELEGRAM_CHAT_ID):
        print("[telegram disabled]\n" + text)
        return None
    data = {"chat_id": C.TELEGRAM_CHAT_ID, "text": text[:4000], "parse_mode": "HTML",
            "disable_web_page_preview": True}
    if buttons:
        data["reply_markup"] = {"inline_keyboard": [[{"text": l, "callback_data": d} for l, d in row] for row in buttons]}
    res = _tg("sendMessage", data)
    return res.get("message_id") if res else None


def send_photo(png, caption=""):
    if not png:
        return None
    if not (C.TELEGRAM_TOKEN and C.TELEGRAM_CHAT_ID):
        print(f"[telegram disabled] photo {len(png)} bytes: {caption}")
        return None
    res = _tg("sendPhoto", {"chat_id": C.TELEGRAM_CHAT_ID, "caption": caption[:1000], "parse_mode": "HTML"},
              files={"photo": ("chart.png", png, "image/png")})
    return res.get("message_id") if res else None


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
    tr = c.get("trends") or {}
    if tr.get("ratio") is not None:
        L.append(f"🔍 Google: החיפושים פי {tr['ratio']} מהשבוע שעבר")
    if c.get("pattern") is not None:
        star = "🎯🎯" if c["pattern"] == 4 else "🎯" if c["pattern"] == 3 else "▫️"
        L.append(f"{star} דפוס היסטורי: {c['pattern']}/4" + (f" ({e('; '.join(c['pattern_hits']))})" if c["pattern_hits"] else ""))
    if c.get("flags"):
        L.append(" · ".join(e(f) for f in c["flags"]))
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
    if c.get("price"):
        p = c["price"]
        L.append(f"📏 כללי הניסוי: סטופ {p * (1 - C.STOP_PCT):.2f} (−{C.STOP_PCT:.0%}) · "
                 f"מימוש {p * (1 + C.TP_PCT):.2f} (+{C.TP_PCT:.0%}) · עד {C.HOLD_DAYS} ימים · "
                 f"גודל עד {C.POSITION_PCT:g}% מהתיק")
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


def _fmt_stats(st):
    if not st["evaluated"]:
        return f"{st['n']} התראות, עוד אין מספיק זמן לתוצאות"
    parts = [f"{st['n']} התראות", f"+20% תוך 3 ימים: {st['hit20']}%", f"−15%: {st['dd15']}%"]
    if st["sim_n"]:
        parts.append(f"עסקת ניסוי ממוצעת: {st['sim_mean']:+.1f}% ({st['sim_win']}% רווחיות)")
    return " · ".join(parts)


def fmt_weekly(week_stats, all_stats, groups, top, pages_url=""):
    L = ["📊 <b>MemeRadar: סיכום שבועי</b>", f"<b>השבוע:</b> {_fmt_stats(week_stats)}",
         f"<b>מההתחלה:</b> {_fmt_stats(all_stats)}"]
    if all_stats.get("sim_total") is not None:
        L.append(f"אילו נכנסת לכל התראה לפי כללי הניסוי: סה\"כ {all_stats['sim_total']:+.1f}% (סכום אחוזים, לפני מס)")
    good = [(k, v) for k, v in groups.items() if v["evaluated"] >= 3]
    if good:
        L.append("\n<b>מה עובד (לפחות 3 התראות עם תוצאה):</b>")
        for k, v in sorted(good, key=lambda kv: -(kv[1]["sim_mean"] or -99))[:8]:
            sm = f", ניסוי {v['sim_mean']:+.1f}%" if v["sim_mean"] is not None else ""
            L.append(f"• {e(k)}: +20% ב-{v['hit20']}%, −15% ב-{v['dd15']}%{sm} (n={v['evaluated']})")
    if top:
        L.append("\n<b>ההתראות של השבוע:</b>")
        for x in top[:8]:
            o = x["out"]
            m = f"שיא {o['max3d'] * 100:+.0f}% / שפל {o['min3d'] * 100:+.0f}%" if "max3d" in o else "ממתין לתוצאה"
            fb = {1: " 👍", -1: " 👎"}.get(x.get("fb"), "")
            L.append(f"• ${e(x['ticker'])} ({e(' + '.join(x['sources']))}): {m}{fb}")
    if pages_url:
        L.append(f"\n<a href='{e(pages_url)}'>לוח הבקרה המלא</a>")
    L.append("<i>תוצאות על נייר. עם מעט התראות המספרים עוד רועשים מאוד.</i>")
    return "\n".join(L)


HELP = """🤖 <b>פקודות MemeRadar</b>
/status: מה המצב עכשיו
/open: התראות פתוחות
/watch GME: מעקב צמוד אחרי מניה
/unwatch GME: הסרה ממעקב
/list: רשימת המעקב שלך
/quiet 8: השתקה ל-8 שעות (ההתראות יישמרו ויישלחו אחר כך)
/unquiet: ביטול השתקה
/report: הסיכום השבועי עכשיו
/help: הרשימה הזו
<i>הסורק קורא פקודות פעם ב-15 דקות, אז התשובה מגיעה בהשהיה.</i>"""


def fmt_status(state, journal_stats, pages_url=""):
    import time as _t
    now = _t.time()
    last = state.get("last_run") or 0
    L = ["🩺 <b>סטטוס</b>", f"ריצה אחרונה: לפני {int((now - last) / 60)} דקות" if last else "עוד לא הייתה ריצה מלאה"]
    for name, (ok, bad) in sorted((state.get("health") or {}).get("src", {}).items()):
        L.append(f"{'✅' if bad == 0 else ('⚠️' if ok else '❌')} {e(name)}: {ok}/{ok + bad} הצליחו היום")
    opened = [t for t, a in state.get("alerts", {}).items() if not a.get("closed")]
    L.append(f"התראות פתוחות: {', '.join('$' + t for t in opened) or 'אין'}")
    L.append(f"מעקב צמוד: {', '.join('$' + t for t in state.get('watch', [])) or 'אין'}")
    q = state.get("quiet_until", 0)
    if q > now:
        L.append(f"🔕 מושתק עוד {int((q - now) / 3600) + 1} שעות")
    x = state.get("x") or {}
    if x.get("day"):
        L.append(f"X: ${x.get('spent', 0):.2f} היום")
    L.append(f"יומן: {_fmt_stats(journal_stats)}")
    errs = [x for x in state.get("last_errors", []) if now - x[0] < 86400]
    if errs:
        L.append(f"⚠️ תקלות ב-24 השעות האחרונות: {len(errs)}. האחרונה: <code>{e(errs[-1][1] + ': ' + errs[-1][2])}</code>")
    if pages_url:
        L.append(f"<a href='{e(pages_url)}'>לוח הבקרה</a>")
    return "\n".join(L)
