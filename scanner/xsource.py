"""X (Twitter) API v2, pay-per-use. Every call is charged, so everything goes through a daily budget."""
import time

import requests

from . import config as C

API = "https://api.x.com/2"


class XClient:
    def __init__(self, state):
        self.st = state.setdefault("x", {"day": "", "spent": 0.0, "since": {}, "uid": {}, "watch_i": 0})
        today = time.strftime("%Y%m%d", time.gmtime())
        if self.st["day"] != today:
            self.st.update(day=today, spent=0.0)
        self.ok = bool(C.X_BEARER_TOKEN)
        self.errors = 0

    def _can(self, cost):
        return self.ok and self.st["spent"] + cost <= C.X_DAILY_BUDGET

    def _get(self, path, params, cost_fn):
        try:
            r = requests.get(API + path, params=params, timeout=20,
                             headers={"Authorization": f"Bearer {C.X_BEARER_TOKEN}"})
        except requests.RequestException:
            self.errors += 1
            return None
        if r.status_code != 200:
            print("x api", path, r.status_code, r.text[:200])
            self.errors += 1
            if r.status_code in (401, 403):
                self.ok = False
            return None
        j = r.json()
        self.st["spent"] = round(self.st["spent"] + cost_fn(j), 4)
        return j

    def counts(self, ticker):
        """Hourly post counts for $TICKER over the last 7 days -> (last_hour, hourly_mean_before)."""
        if not self._can(C.X_COST["count"]):
            return None
        j = self._get("/tweets/counts/recent", {"query": f"${ticker} -is:retweet", "granularity": "hour"},
                      lambda j: C.X_COST["count"])
        if not j or not j.get("data"):
            return None
        vals = [d["tweet_count"] for d in j["data"]]
        # the last bucket is the current, partial hour: use the last complete hour
        last = vals[-2] if len(vals) >= 2 else vals[-1]
        base = vals[:-7] or vals[:-1] or [0]
        return {"x_1h": last, "x_base_h": sum(base) / len(base), "x_24h": sum(vals[-25:-1])}

    def account_posts(self, username):
        """New posts from a watched account since the last check (first call only sets the marker)."""
        uid = self.st["uid"].get(username)
        if not uid:
            if not self._can(C.X_COST["user"]):
                return []
            j = self._get(f"/users/by/username/{username}", {}, lambda j: C.X_COST["user"])
            if not j or "data" not in j:
                return []
            uid = self.st["uid"][username] = j["data"]["id"]
        if not self._can(C.X_COST["post"] * 5):
            return []
        params = {"max_results": 5, "tweet.fields": "created_at", "exclude": "retweets"}
        since = self.st["since"].get(username)
        if since:
            params["since_id"] = since
        j = self._get(f"/users/{uid}/tweets", params, lambda j: C.X_COST["post"] * len(j.get("data") or []))
        posts = (j or {}).get("data") or []
        if posts:
            self.st["since"][username] = max(posts, key=lambda p: int(p["id"]))["id"]
        return posts if since else []  # first run: just remember where we are

    def next_watch(self):
        if not C.X_WATCHLIST:
            return None
        i = self.st.get("watch_i", 0) % len(C.X_WATCHLIST)
        self.st["watch_i"] = i + 1
        return C.X_WATCHLIST[i].strip().upper()
