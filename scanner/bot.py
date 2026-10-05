"""Telegram commands and 👍/👎 buttons, handled at the start of every run (polling, no server needed)."""
import re
import time

from . import config as C
from . import journal, notify

TICKER = re.compile(r"^\$?([A-Za-z]{1,5})$")


def poll(state, jr, on_report):
    """Read new Telegram updates and act on them. Only messages from TELEGRAM_CHAT_ID are obeyed."""
    res = notify._tg("getUpdates", {"offset": state.get("tg_offset", 0), "timeout": 0,
                                    "allowed_updates": ["message", "callback_query"]})
    if not res:
        return 0
    n = 0
    for u in res:
        state["tg_offset"] = u["update_id"] + 1
        if "callback_query" in u:
            q = u["callback_query"]
            if str(q.get("message", {}).get("chat", {}).get("id")) != str(C.TELEGRAM_CHAT_ID):
                continue
            handle_callback(q, jr)
            n += 1
        elif "message" in u:
            m = u["message"]
            if str(m.get("chat", {}).get("id")) != str(C.TELEGRAM_CHAT_ID):
                continue
            handle_command(m.get("text") or "", state, jr, on_report)
            n += 1
    return n


def handle_callback(q, jr):
    data = q.get("data") or ""
    parts = data.split("|")
    if len(parts) == 3 and parts[0] == "fb":
        val = 1 if parts[2] == "1" else -1
        e = journal.set_feedback(jr, parts[1], val)
        notify._tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "נרשם, תודה"})
        if e:
            label = "✓ סימנת: מעניין 👍" if val > 0 else "✓ סימנת: רעש 👎"
            notify._tg("editMessageReplyMarkup", {
                "chat_id": C.TELEGRAM_CHAT_ID, "message_id": q["message"]["message_id"],
                "reply_markup": {"inline_keyboard": [[{"text": label, "callback_data": "noop"}]]}})


def handle_command(text, state, jr, on_report):
    parts = text.strip().split()
    if not parts or not parts[0].startswith("/"):
        notify.send("שלח /help לרשימת הפקודות")
        return
    cmd = parts[0].split("@")[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    watch = state.setdefault("watch", [])
    if cmd in ("/help", "/start"):
        notify.send(notify.HELP)
    elif cmd == "/status":
        notify.send(notify.fmt_status(state, journal.stats(journal.main_entries(jr["entries"])), C.PAGES_URL))
    elif cmd == "/open":
        opened = {t: a for t, a in state.get("alerts", {}).items() if not a.get("closed")}
        if not opened:
            notify.send("אין התראות פתוחות")
        else:
            lines = ["📂 <b>התראות פתוחות</b>"]
            for t, a in opened.items():
                ch = ""
                if a.get("entry_price") and a.get("last_price"):
                    ch = f" · {(a['last_price'] / a['entry_price'] - 1) * 100:+.1f}%"
                lines.append(f"${t} · ציון {a.get('score')} · לפני {int((time.time() - a['time']) / 3600)} שעות{ch}")
            notify.send("\n".join(lines))
    elif cmd in ("/watch", "/unwatch"):
        m = TICKER.match(arg)
        if not m:
            notify.send(f"כתוב למשל: {cmd} GME")
            return
        t = m.group(1).upper()
        if cmd == "/watch":
            if t not in watch:
                watch.append(t)
            notify.send(f"👀 ${t} במעקב צמוד. אבדוק אותו בכל המקורות בכל ריצה.")
        else:
            if t in watch:
                watch.remove(t)
            notify.send(f"${t} הוסר מהמעקב")
    elif cmd == "/list":
        notify.send("מעקב צמוד: " + (", ".join("$" + t for t in watch) or "ריק. הוסף עם /watch GME"))
    elif cmd == "/quiet":
        hours = int(arg) if arg.isdigit() else 8
        state["quiet_until"] = time.time() + hours * 3600
        notify.send(f"🔕 מושתק ל-{hours} שעות. התראות שיגיעו בינתיים יישלחו כסיכום אחר כך.")
    elif cmd == "/unquiet":
        state["quiet_until"] = 0
        notify.send("🔔 ההשתקה בוטלה")
    elif cmd == "/report":
        on_report(force=True)
    else:
        notify.send("לא הכרתי את הפקודה. שלח /help")


def feedback_buttons(eid):
    return [[("👍 מעניין", f"fb|{eid}|1"), ("👎 רעש", f"fb|{eid}|0")]]
