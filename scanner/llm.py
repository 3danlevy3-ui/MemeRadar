"""Optional: Claude reads a sample of the posts and judges the tone (needs ANTHROPIC_API_KEY)."""
import json
import re

import requests

from . import config as C

PROMPT = """You analyse Reddit chatter about the stock ${t} for an early meme-stock detector.
Below are up to 60 recent comments/posts that mention it. Return ONLY a JSON object:
{{"sentiment": -1..1 (bearish..bullish),
  "hype": 0-10 (rockets, "to the moon", YOLO, FOMO language),
  "squeeze_talk": true/false (short squeeze, short interest, gamma, borrow fee),
  "dd_quality": 0-10 (real due diligence vs pure memes),
  "pump_suspect": true/false (copy-paste, brand-new accounts style, coordinated shilling),
  "catalyst": "one short phrase or empty",
  "summary_he": "one sentence in Hebrew: what people are saying and why now"}}

TEXTS:
{texts}"""


def analyse(ticker, texts):
    if not C.ANTHROPIC_API_KEY or not texts:
        return None
    body = "\n---\n".join(t[:400] for t in texts[:60])
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=60,
                          headers={"x-api-key": C.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"},
                          json={"model": C.CLAUDE_MODEL, "max_tokens": 400,
                                "messages": [{"role": "user", "content": PROMPT.format(t=ticker, texts=body)}]})
        if not r.ok:
            print("claude error", r.status_code, r.text[:200])
            return None
        txt = "".join(b.get("text", "") for b in r.json().get("content", []))
        m = re.search(r"\{.*\}", txt, re.S)
        return json.loads(m.group(0)) if m else None
    except (requests.RequestException, ValueError) as e:
        print("claude error", e)
        return None
