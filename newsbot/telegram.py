"""Telegram alerts and the morning digest. Does nothing if no bot token is set."""
import datetime as dt
import html
import os

import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
LABELS = {"KA": "Karnataka", "TN": "Tamil Nadu", "TG": "Telangana", "AP": "Andhra Pradesh",
          "KL": "Kerala", "IN": "National", "ai_buzz": "AI Buzz", "ai_hacks": "AI Hack"}


def tab_of(s):
    return s["section"] if s["section"] != "news" else (s.get("state") or "IN")


def _send(text, log):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=20)
        if r.status_code != 200:
            log(f"  Telegram error {r.status_code}: {r.text[:150]}")
        return r.status_code == 200
    except Exception as e:  # noqa: BLE001
        log(f"  Telegram error: {e}")
        return False


def _line(s, site_url):
    e = html.escape
    first = s["items"][0]["link"] if s["items"] else site_url
    text = f"<b>[{e(LABELS.get(tab_of(s), ''))}]</b> {e(s['title'])}\n{e(s['summary'][:300])}"
    if s.get("tip"):
        text += f"\n💡 {e(s['tip'][:300])}"
    text += f"\n<i>{s.get('n_sources', 1)} sources</i> · <a href=\"{e(first)}\">read</a>"
    return text


def run_alerts(stories, state, cfg, site_url, log):
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        return
    now = dt.datetime.now(IST)
    q_from, q_to = cfg.get("quiet_from", 23), cfg.get("quiet_to", 7)
    quiet = (now.hour >= q_from or now.hour < q_to) if q_from > q_to else q_from <= now.hour < q_to

    # Morning digest, once a day
    hour = cfg.get("daily_digest_hour", -1)
    today = now.strftime("%Y-%m-%d")
    if hour >= 0 and now.hour >= hour and state.get("last_digest") != today and not quiet:
        top = sorted(stories.values(), key=lambda s: -s.get("score", 0))[:10]
        if top:
            body = "\n\n".join(_line(s, site_url) for s in top)
            if _send(f"☀️ <b>Morning digest</b>\n\n{body}\n\n{site_url}", log):
                state["last_digest"] = today

    if quiet:
        return
    allowed = set(cfg.get("alert_on", []))
    due = [s for s in stories.values()
           if not s.get("alerted") and s.get("score", 0) >= cfg.get("alert_min_score", 4)
           and tab_of(s) in allowed]
    due.sort(key=lambda s: -s["score"])
    limit = cfg.get("max_alerts_per_run", 5)
    for s in due[:limit]:
        if _send("🔥 " + _line(s, site_url), log):
            s["alerted"] = True
    if len(due) > limit:
        if _send(f"…and {len(due) - limit} more trending stories: {site_url}", log):
            for s in due[limit:]:
                s["alerted"] = True
