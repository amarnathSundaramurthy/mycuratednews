"""Turns new articles into stories: delta check, grouping, tagging, scoring."""
import hashlib
import re
import time

from rapidfuzz import fuzz

STATES = {"KA", "TN", "TG", "AP", "KL", "IN"}
SECTIONS = {"news", "ai_buzz", "ai_hacks"}

# Simple keyword lists used when the AI is not available
STATE_WORDS = {
    "KA": r"karnataka|bengaluru|bangalore|mysuru|mysore|mangaluru|mangalore|hubballi|belagavi|"
          r"ಕರ್ನಾಟಕ|ಬೆಂಗಳೂರು",
    "TN": r"tamil nadu|chennai|coimbatore|madurai|tiruchi|trichy|salem|தமிழ்நாடு|சென்னை",
    "TG": r"telangana|hyderabad|warangal|secunderabad|తెలంగాణ|హైదరాబాద్",
    "AP": r"andhra pradesh|vijayawada|visakhapatnam|vizag|amaravati|tirupati|guntur|ఆంధ్ర",
    "KL": r"kerala|kochi|thiruvananthapuram|kozhikode|thrissur|കേരള|കൊച്ചി",
}
HACK_WORDS = re.compile(r"\b(tip|tips|trick|tricks|hack|hacks|how i|how to|prompt|"
                        r"workflow|guide|use case|cheat ?sheet)\b", re.I)


def key_for(item):
    """Two keys per article: its link and its normalised title."""
    link = re.sub(r"[?#].*$", "", item["link"]).rstrip("/").lower()
    title = re.sub(r"\W+", " ", item["title"].lower()).strip()
    return (hashlib.sha1(link.encode()).hexdigest()[:16],
            hashlib.sha1(title.encode()).hexdigest()[:16])


def pick_new(items, seen, keep_hours, limit):
    """Delta step: keep only articles we have never seen, newest first."""
    now = time.time()
    fresh, batch_keys = [], set()
    for it in sorted(items, key=lambda x: -x["ts"]):
        if not it["title"] or now - it["ts"] > keep_hours * 3600:
            continue
        k1, k2 = key_for(it)
        if k1 in seen or k2 in seen or k1 in batch_keys or k2 in batch_keys:
            continue
        batch_keys.update((k1, k2))
        fresh.append(it)
    for it in fresh[:limit]:
        for k in key_for(it):
            seen[k] = int(now)
    return fresh[:limit]


def guess_state(text):
    for code, pat in STATE_WORDS.items():
        if re.search(pat, text, re.I):
            return code
    return None


def new_story_id():
    return "s" + hashlib.sha1(str(time.time_ns()).encode()).hexdigest()[:10]


# ------------------------------------------------------------- AI grouping
SYSTEM = """You are a news desk editor for an Indian news dashboard focused on South India
(Karnataka, Tamil Nadu, Telangana, Andhra Pradesh, Kerala) plus national news and AI.
Articles may be in English, Kannada, Tamil, Telugu or Malayalam. Always answer in English.
Reply with JSON only."""

PROMPT = """EXISTING STORIES (id: title):
{existing}

NEW ARTICLES (number. [source | hint] title — snippet):
{articles}

Tasks:
1. Put each new article into a story. If it is about the SAME event as an existing story,
   use that story id. Otherwise create a new story with a temporary id "N1", "N2", ...
   Articles in different languages about the same event belong to the same story.
2. For each article give:
   state: KA, TN, TG, AP, KL (main South Indian state involved), IN (national/other India),
          or OTHER (not about India and not AI).
   section: "news" for normal news; "ai_buzz" for AI releases, research, company or policy news;
            "ai_hacks" for practical tips, tricks, prompts or workflows people share for using AI;
            "skip" for ads, horoscopes, quizzes, spam, or content with no news value.
3. For every NEW story and every existing story that got new articles, write:
   title: short clear English headline (max 14 words)
   summary: 2-3 plain English sentences, facts only
   tip: only for ai_hacks - the actual tip in one or two lines; otherwise ""

JSON format:
{{"articles": [{{"n": 1, "story": "N1", "state": "KA", "section": "news"}}],
  "stories": [{{"story": "N1", "title": "...", "summary": "...", "tip": ""}}]}}"""


def _hint(it):
    return f"{it['state'] or '?'}/{it['section']}"


def group_with_llm(llm, batch, stories, log):
    recent = sorted(stories.values(), key=lambda s: -s["updated"])[:120]
    existing = "\n".join(f"{s['id']}: {s['title']}" for s in recent) or "(none yet)"
    arts = "\n".join(
        f"{i + 1}. [{it['source']} | {_hint(it)}] {it['title']} — {it['summary'][:200]}"
        for i, it in enumerate(batch))
    data = llm.ask_json(SYSTEM, PROMPT.format(existing=existing, articles=arts))
    if not isinstance(data, dict) or not isinstance(data.get("articles"), list):
        return None
    texts = {str(s.get("story")): s for s in data.get("stories", []) if isinstance(s, dict)}
    result = []
    for a in data["articles"]:
        try:
            n = int(a.get("n")) - 1
        except (TypeError, ValueError):
            continue
        if not 0 <= n < len(batch):
            continue
        result.append((batch[n], str(a.get("story", "")), a.get("state"), a.get("section"),
                       texts.get(str(a.get("story")))))
    done = {id(r[0]) for r in result}
    missing = [it for it in batch if id(it) not in done]
    if missing:
        log(f"  AI skipped {len(missing)} articles; grouping them by title instead")
    return result, missing


# ---------------------------------------------------------- simple grouping
def group_simple(batch, stories):
    result = []
    pool = [(s["id"], s["title"].lower()) for s in stories.values()]
    for n, it in enumerate(batch):
        title = it["title"].lower()
        best, best_score = None, 0
        for pid, ptitle in pool:
            sc = (fuzz.token_set_ratio(title, ptitle) + fuzz.token_sort_ratio(title, ptitle)) / 2
            if sc > best_score:
                best, best_score = pid, sc
        if best and best_score >= 82:
            sid = best
        else:
            sid = f"T{n}"
            pool.append((sid, title))
        state = it["state"] or guess_state(it["title"] + " " + it["summary"]) or "IN"
        section = it["section"]
        if section == "ai":
            section = "ai_hacks" if HACK_WORDS.search(it["title"]) else "ai_buzz"
        result.append((it, sid, state, section, None))
    return result


# ------------------------------------------------------------------ merge
def merge(results, stories, used_ai):
    now = int(time.time())
    temp_ids = {}
    for it, sid, state, section, text in results:
        if section == "skip" or state == "OTHER" and section == "news":
            continue
        if section not in SECTIONS:
            section = "news" if it["section"] == "news" else "ai_buzz"
        if section != "news":
            state = None
        elif state not in STATES:
            state = it["state"] or "IN"

        if sid in stories:
            s = stories[sid]
        elif sid and sid in temp_ids:
            s = stories[temp_ids[sid]]
        else:
            s = {"id": new_story_id(), "title": it["title"], "summary": it["summary"],
                 "tip": "", "state": state, "section": section, "created": now,
                 "updated": now, "items": [], "alerted": False, "ai": used_ai}
            stories[s["id"]] = s
            if sid:
                temp_ids[sid] = s["id"]
        s["items"].append({"title": it["title"], "link": it["link"], "source": it["source"],
                           "ts": it["ts"], "lang": it["lang"], "score": it.get("score", 0),
                           "added": now})
        s["updated"] = now
        if text:
            s["title"] = (text.get("title") or s["title"])[:200]
            s["summary"] = (text.get("summary") or s["summary"])[:700]
            s["tip"] = (text.get("tip") or s.get("tip", ""))[:400]
            s["ai"] = True
        elif not s["summary"]:
            s["summary"] = it["summary"]


def score(s, now=None):
    now = now or time.time()
    sources = {i["source"].split(" / ")[-1].lower() for i in s["items"]}
    recent = sum(1 for i in s["items"] if now - i["added"] < 3 * 3600)
    engagement = max((i.get("score", 0) for i in s["items"]), default=0)
    bonus = 1 if engagement >= 200 else 0
    s["n_sources"] = len(sources)
    s["score"] = round(len(sources) + 0.5 * recent + bonus, 1)
    return s["score"]


def prune(stories, seen, keep_hours):
    now = time.time()
    for sid in [k for k, s in stories.items() if now - s["updated"] > keep_hours * 3600]:
        del stories[sid]
    for k in [k for k, t in seen.items() if now - t > 7 * 86400]:
        del seen[k]
