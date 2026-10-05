"""Plain-language Telegram messages: what happened, why it matters, what weakens it. Tech details folded."""
import html

from . import config as C

e = html.escape


def money(p):
    if p is None:
        return "?"
    return f"{p:,.2f}" if p >= 1 else f"{p:.4f}"


def strength(score):
    n = 1 if score < 40 else 2 if score < 55 else 3 if score < 70 else 4 if score < 85 else 5
    return "●" * n + "○" * (5 - n)


def _ratio(x, new):
    return "" if new else f", פי {x:g} מבדרך כלל"


def reasons(c, llm=None):
    """Return (why, plus, minus) lists of short Hebrew sentences."""
    why, plus, minus = [], [], []
    src = c.get("sources") or []
    places = [s for s in src if s in ("Reddit", "Stocktwits", "X")]
    if c.get("influencer"):
        why.append(f"@{e(c['influencer'])} פרסם עכשיו פוסט שמזכיר אותה")
    if places:
        loud = []
        if "Reddit" in places and c.get("mentions_1h"):
            loud.append(f"ברדיט {c['mentions_1h']} אזכורים בשעה{_ratio(c.get('burst', 0), c.get('reddit_new'))}")
        if "Stocktwits" in places and c.get("st_1h") is not None:
            loud.append(f"ב-Stocktwits {c['st_1h']} הודעות בשעה{_ratio(c.get('st_burst') or 0, c.get('st_new'))}")
        if "X" in places and c.get("x_1h") is not None:
            loud.append(f"ב-X {c['x_1h']} פוסטים בשעה, פי {c.get('x_burst')} מבדרך כלל")
        new = (c.get("reddit_new") and "Reddit" in places) or (c.get("st_new") and "Stocktwits" in places)
        why.append("פתאום מדברים עליה: " + "; ".join(loud) + (" (עד עכשיו כמעט לא דיברו עליה)" if new else "")
                   if loud else "פתאום מדברים עליה הרבה יותר מבדרך כלל")
    if c.get("fast"):
        why.append("השיח מאיץ ממש עכשיו: ב-20 הדקות האחרונות הקצב גבוה מהממוצע של השעה")
    if (c.get("authors_1h") or 0) >= 5:
        why.append(f"{c['authors_1h']} אנשים שונים כתבו עליה בשעה האחרונה, לא אדם אחד שמספים")
    if c.get("st_bull") is not None and c["st_bull"] >= 0.7:
        why.append(f"{int(c['st_bull'] * 100)}% מהכותבים אופטימיים")
    elif c.get("st_bull") is not None and c["st_bull"] <= 0.4:
        minus.append(f"רוב הכותבים פסימיים ({int((1 - c['st_bull']) * 100)}% צופים ירידה)")

    if len(places) >= 2:
        plus.append("מדברים עליה ביותר ממקום אחד")
    if c.get("pattern", 0) >= 3:
        plus.append(f"מתאימה ל-{c['pattern']} מתוך 4 התנאים שהופיעו לפני זינוקים בעבר")
    if any("מאפס" in f for f in c.get("flags") or []):
        plus.append("עד עכשיו כמעט אף אחד לא דיבר עליה. ככה התחילו רוב ההצלחות בעבר")
    if (c.get("rel_volume") or 0) >= 2:
        plus.append(f"נסחרות פי {c['rel_volume']:g} יותר מניות מבדרך כלל, כלומר גם כסף אמיתי זז")
    si = c.get("si") or {}
    if (si.get("dtc") or 0) >= C.DTC_HIGH:
        plus.append("הרבה משקיעים מהמרים על ירידה. אם המחיר יעלה, הם ייאלצו לקנות, וזה דוחף עוד למעלה")
    elif si.get("dtc") is not None and si["dtc"] < 3:
        minus.append("מעט מהמרים על ירידה, אז אין 'דלק' לזינוק חד")
    opt = c.get("options") or {}
    if (opt.get("cp_ratio") or 0) >= 3:
        plus.append("קונים הרבה אופציות שמהמרות על עלייה")
    tr = (c.get("trends") or {}).get("ratio")
    if tr is not None and tr >= 2:
        plus.append(f"גם בגוגל מחפשים אותה יותר (פי {tr:g}). ההייפ יוצא החוצה לציבור הרחב")
    elif tr is not None and tr < 1:
        minus.append("בגוגל לא מחפשים אותה יותר מהרגיל. הציבור הרחב עוד לא שם לב")
    if (c.get("mcap_b") or 0) >= C.BIG_CAP_BUSD:
        minus.append(f"חברה גדולה מאוד (שווי של כ-{c['mcap_b']:.0f} מיליארד $). קשה להזיז אותה רק בגלל הייפ")
    if c.get("tier") == "MOMENTUM" and c.get("market_live") is not False:
        minus.append(f"המחיר כבר עלה {c.get('move_24h', 0):.0f}% ביממה. ייתכן שחלק מהעלייה כבר מאחורינו")
    for f in c.get("flags") or []:
        if "ספאם" in f:
            minus.append("נראה שחלק מההודעות משוכפלות או מאותו אדם, ייתכן שמנסים לנפח אותה")
        if "דוחות" in f:
            minus.append("החברה מפרסמת דוחות כספיים בימים אלה, אז טבעי שמדברים עליה")
    if llm and llm.get("summary_he"):
        why.append("על מה מדברים: " + e(llm["summary_he"]))
    elif c.get("st_summary"):
        why.append("על מה מדברים (Stocktwits, באנגלית): " + e(c["st_summary"][:220]))
    return why, plus, minus


def headline(c):
    name = e(c.get("name") or c["ticker"])
    t = e(c["ticker"])
    if c.get("influencer"):
        return f"⭐ <b>{name} (${t})</b>: פוסט חדש של משפיע"
    if c.get("market_live") is False:
        return f"🌙 <b>{name} (${t})</b>: מדברים עליה בזמן שהבורסה סגורה"
    if c.get("tier") == "MOMENTUM":
        return f"🟠 <b>{name} (${t})</b>: מדברים עליה, והמחיר כבר עולה"
    return f"🟢 <b>{name} (${t})</b>: התחילו לדבר עליה, והמחיר עוד לא זז"


def fmt_alert(c, llm=None, technical="", extreme=False):
    why, plus, minus = reasons(c, llm)
    L = [fmt_extreme_block(c), ""] if extreme else []
    L += [headline(c), f"חוזק האות: {strength(c.get('score', 0))}", ""]
    if why:
        L.append("<b>למה קיבלת את זה:</b>")
        L += [f"• {x}" for x in why]
    if plus:
        L.append("\n<b>מה מחזק:</b>")
        L += [f"✓ {x}" for x in plus]
    if minus:
        L.append("\n<b>מה מחליש:</b>")
        L += [f"✗ {x}" for x in minus]
    if c.get("price") is not None:
        mv = c.get("move_24h") or 0
        if c.get("market_live") is False:
            L.append(f"\n<b>המחיר:</b> {money(c['price'])}$ בסגירה האחרונה. "
                     f"ביום המסחר האחרון {'עלה' if mv >= 0 else 'ירד'} {abs(mv):.0f}%.")
            L.append("🌙 הבורסה סגורה עכשיו. ההתראה היא על השיח בלבד, והמחיר יתעדכן בפתיחה (16:30 שעון ישראל, טרום-מסחר מ-11:00).")
        else:
            L.append(f"\n<b>המחיר:</b> {money(c['price'])}$, "
                     f"{'עלה' if mv >= 0 else 'ירד'} {abs(mv):.0f}% ביממה האחרונה")
        p = c["price"]
        L.append(f"📏 אם נכנסים (ניסוי, לא המלצה): לצאת בהפסד מתחת ל-{money(p * (1 - C.STOP_PCT))}, "
                 f"ברווח מעל {money(p * (1 + C.TP_PCT))}, ולא להחזיק יותר מ-{C.HOLD_DAYS} ימים.")
    if technical:
        L.append(f"<blockquote expandable>{technical}</blockquote>")
    L.append("<i>זה סימן לתנועה חזקה, לא הבטחה לעלייה.</i>")
    return "\n".join(L)


def fmt_exit(x):
    r = x.get("ret")
    ch = f"{'+' if r >= 0 else ''}{r * 100:.0f}%" if r is not None else "?"
    reason = x["reason"]
    if "below the peak" in reason:
        why = f"המחיר ירד {int(C.EXIT_TRAIL_STOP * 100)}% מהשיא שלו מאז ההתראה"
    elif "faded" in reason:
        why = "השיח נרגע: מדברים עליה הרבה פחות"
    else:
        why = f"עברו {C.EXIT_MAX_HOURS} שעות מההתראה"
    return (f"🔴 <b>${e(x['ticker'])}: כדאי לשקול יציאה</b>\n{why}.\n"
            f"שינוי במחיר מאז ההתראה: {ch}")


def digest_line(d):
    arrow = "🔥" if d.get("hot") else "➖"
    return (f"{arrow} <b>{e(d.get('name') or d['ticker'])} (${e(d['ticker'])})</b> {strength(d.get('score', 0))}\n"
            f"   {e(d.get('why') or '')}")


def fmt_digest(items, problems=None, pages_url=""):
    L = ["📋 <b>מה מתחמם היום</b>",
         "<i>מניות שהתחילו לדבר עליהן, אבל עוד לא מספיק חזק או מספיק זמן בשביל התראה מיידית.</i>", ""]
    if items:
        L += [digest_line(d) for d in items[:12]]
        L.append("\n🔥 = עדיין חם בשעתיים האחרונות · ➖ = נרגע")
    else:
        L.append("היום שקט. אף מניה לא התחממה במיוחד.")
    if problems:
        L.append("\n⚠️ <b>מקורות שלא עבדו היום:</b> " + ", ".join(e(p) for p in problems))
    if pages_url:
        L.append(f"\n<a href='{e(pages_url)}'>לוח הבקרה</a>")
    return "\n".join(L)


def fmt_extreme_block(c):
    t = e(c["ticker"])
    L = [f"🚨🚨 <b>פעילות חריגה מאוד: {e(c.get('name') or c['ticker'])} (${t})</b>", "<b>מה חריג:</b>"]
    L += [f"‼️ {x}" for x in c.get("extreme_reasons") or []]
    L.append("\n<b>מה לעשות עכשיו:</b>")
    L.append(f"1. לפתוח את השיח (הקישורים בפרטים למטה) ולבדוק: יש חדשות אמיתיות, או רק הייפ?")
    if c.get("market_live") is False:
        L.append("2. הבורסה סגורה. המחיר הראשון יופיע בטרום-מסחר (מ-11:00 שעון ישראל). לבדוק שם אם המחיר כבר קפץ.")
    else:
        L.append("2. לבדוק את המחיר עכשיו: אם הוא כבר קפץ חזק, ייתכן שהחלק הקל של העלייה מאחורינו.")
    L.append("3. אם נכנסים: רק סכום קטן, ועם פקודת סטופ מראש (המחירים בשורת 📏).")
    L.append("4. ללחוץ 👍 או 👎 בהמשך, כדי שנלמד אם ההתראות החריגות שוות משהו.")
    return "\n".join(L)
