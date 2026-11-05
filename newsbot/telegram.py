"""Telegram digest: sends only stories that were not sent before (delta), grouped by section.

Does nothing if the bot token or chat ID is not set (and says so in the log).
"""
import datetime as dt
import html
import os
import time

import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
MAX_MESSAGE = 3900  # Telegram allows 4096 characters per message; keep a safety margin

# (heading, cap key in config, default cap, rule that picks the stories)
SECTIONS = [
    ("Karnataka", "karnataka", 8,
     lambda s: s["section"] == "news" and s.get("state") == "KA"),
    ("Tamil Nadu", "tamil_nadu", 5,
     lambda s: s["section"] == "news" and s.get("state") == "TN"),
    ("India", "india", 6,
     lambda s: s["section"] == "news" and s.get("state") in (None, "IN", "TG", "AP", "KL")),
    ("Tech & Business", "tech_business", 4,
     lambda s: s["section"] in ("biz", "ai_buzz")),
    ("International", "international", 4,
     lambda s: s["section"] == "news" and s.get("state") == "WORLD"),
]


def _send(text, log):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=20)
        if r.status_code != 200:
            log(f"  Telegram error {r.status_code}: {r.text[:200]}")
        return r.status_code == 200
    except Exception as e:  # noqa: BLE001
        log(f"  Telegram error: {e}")
        return False


def _ordinal(n):
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _bullet(s):
    e = html.escape
    link = s["items"][0]["link"] if s.get("items") else ""
    if link:
        return f'• <a href="{e(link, quote=True)}">{e(s["title"])}</a>'
    return f"• {e(s['title'])}"


def pick(stories, cfg, allowed, now=None):
    """Choose this run's stories: new since last digest, allowed by the rules, within caps."""
    now = now or time.time()
    window = cfg.get("window_hours", 16) * 3600
    caps = cfg.get("caps", {})
    max_total = cfg.get("max_total", 27)
    fresh = [s for s in stories.values()
             if not s.get("sent") and now - s.get("created", 0) <= window and allowed(s)]
    fresh.sort(key=lambda s: (-s.get("score", 0), -s.get("updated", 0)))
    picked, total = [], 0
    for name, key, default_cap, rule in SECTIONS:
        cap = min(caps.get(key, default_cap), max_total - total)
        chosen = [s for s in fresh if rule(s)][:max(cap, 0)]
        if chosen:
            picked.append((name, chosen))
            total += len(chosen)
    return picked


def build_messages(picked, site_url, now=None):
    now = now or dt.datetime.now(IST)
    label = "Morning" if now.hour < 12 else "Evening"
    date = f"{now.strftime('%b')} {_ordinal(now.day)}, {now.year}"
    blocks = [f"<b>{label} Highlights - {date}</b>\n" + "-" * 40]
    for name, chosen in picked:
        blocks.append(f"<b>{name}</b>\n" + "\n".join(_bullet(s) for s in chosen))
    if site_url:
        blocks.append(f'<a href="{html.escape(site_url, quote=True)}">Open the full news page</a>')

    # Split into messages under Telegram's size limit
    messages, current = [], ""
    for block in blocks:
        parts = [block] if len(block) <= MAX_MESSAGE else block.split("\n")
        for part in parts:
            if current and len(current) + len(part) + 2 > MAX_MESSAGE:
                messages.append(current)
                current = ""
            current = f"{current}\n\n{part}" if current else part
    if current:
        messages.append(current)
    return messages


def send_digest(stories, state, cfg, site_url, log, allowed):
    if not os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or \
            not os.environ.get("TELEGRAM_CHAT_ID", "").strip():
        log("   Telegram not set up: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID secret is missing")
        return
    picked = pick(stories, cfg, allowed)
    count = sum(len(c) for _, c in picked)
    if not count:
        log("   Nothing new to send")
        return
    messages = build_messages(picked, site_url)
    if all(_send(m, log) for m in messages):
        for _, chosen in picked:
            for s in chosen:
                s["sent"] = True
        state["last_digest"] = int(time.time())
        log(f"   Sent digest: {count} stories in {len(messages)} message(s)")
    else:
        log("   Digest not fully sent; these stories will be tried again next run")
