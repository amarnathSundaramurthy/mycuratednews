"""One small client for Gemini, Groq and OpenRouter.

All three offer an OpenAI-style "chat completions" address, so the same code
works for each. Providers are tried in order; a provider that hits its limit
is skipped for the rest of the run.
"""
import json
import os
import re
import time

import requests

PROVIDERS = {
    "gemini": ("GEMINI_API_KEY",
               "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"),
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions"),
}


class LLM:
    def __init__(self, model_config, log):
        self.log = log
        self.chain = []  # (provider, model, key, url)
        for provider, models in (model_config or {}).items():
            env, url = PROVIDERS.get(provider, (None, None))
            key = os.environ.get(env or "", "").strip()
            if url and key:
                for m in models or []:
                    self.chain.append((provider, m, key, url))
        self.blocked = set()
        self.calls = 0
        self.used = {}

    @property
    def available(self):
        return any(p not in self.blocked for p, *_ in self.chain)

    def ask_json(self, system, user):
        """Return parsed JSON from the first model that answers, or None."""
        for provider, model, key, url in self.chain:
            if provider in self.blocked:
                continue
            for attempt in range(2):
                try:
                    self.calls += 1
                    r = requests.post(
                        url,
                        headers={"Authorization": f"Bearer {key}",
                                 "Content-Type": "application/json"},
                        json={"model": model,
                              "messages": [{"role": "system", "content": system},
                                           {"role": "user", "content": user}],
                              "temperature": 0.2,
                              "response_format": {"type": "json_object"}},
                        timeout=120,
                    )
                    if r.status_code == 429:
                        body = r.text.lower()
                        daily = "per day" in body or "perday" in body or "daily" in body
                        if daily or attempt == 1:
                            self.log(f"  LLM {provider}: limit reached, skipping it this run")
                            self.blocked.add(provider)
                            break
                        self.log(f"  LLM {provider}/{model}: per-minute limit, waiting 30s")
                        time.sleep(30)
                        continue
                    if r.status_code in (401, 403):
                        self.log(f"  LLM {provider}: key rejected ({r.status_code})")
                        self.blocked.add(provider)
                        break
                    if r.status_code >= 400:
                        self.log(f"  LLM {provider}/{model}: error {r.status_code} {r.text[:150]}")
                        break  # try next model
                    text = r.json()["choices"][0]["message"]["content"]
                    data = parse_json(text)
                    if data is None:
                        self.log(f"  LLM {provider}/{model}: answer was not valid JSON")
                        break
                    self.used[f"{provider}/{model}"] = self.used.get(f"{provider}/{model}", 0) + 1
                    return data
                except Exception as e:  # noqa: BLE001
                    self.log(f"  LLM {provider}/{model}: {type(e).__name__}: {str(e)[:120]}")
                    break
        return None


def parse_json(text):
    if not text:
        return None
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except ValueError:
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b > a:
            try:
                return json.loads(text[a:b + 1])
            except ValueError:
                return None
    return None
