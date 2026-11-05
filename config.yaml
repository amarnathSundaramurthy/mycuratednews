# =====================================================================
#  My Curated News - settings
#  You can edit this file in the GitHub website (click the pencil icon).
#  Lines starting with # are notes and are ignored.
# =====================================================================

settings:
  # How many hours a story stays on the page after its last update
  keep_hours: 72
  # Most new articles handled in one run (keeps AI usage low)
  max_new_items_per_run: 200
  # How many articles go to the AI in one request (smaller = fewer AI timeouts)
  llm_batch_size: 25
  # A story counts as "trending" when this many different sources cover it
  trending_min_sources: 3

  # AI models, tried in this order. If one fails or hits its limit, the next is used.
  # Each provider is only used if its key is set in GitHub Secrets.
  llm:
    gemini:   [gemini-flash-latest, gemini-flash-lite-latest]   # key: GEMINI_API_KEY
    groq:     [llama-3.3-70b-versatile, openai/gpt-oss-120b]   # key: GROQ_API_KEY (optional)
    openrouter: [openrouter/free]                               # key: OPENROUTER_API_KEY (optional)

  telegram:
    # Every run sends one digest with only the stories not sent before.
    # Only stories first seen in the last this-many hours are considered.
    window_hours: 16
    # Show a 2-line brief and a source link under each headline (false = headlines only)
    show_brief: true
    # Most stories in one digest
    max_total: 27
    # Most stories per section
    caps:
      karnataka: 8
      tamil_nadu: 5
      india: 6
      tech_business: 4
      international: 4

# =====================================================================
#  Sources
#  type:     rss | google_news | inshorts | reddit | hackernews
#  section:  news | biz | ai   (ai items are split into AI Buzz and AI Hacks)
#  state:    optional hint - KA TN IN WORLD
#  lang:     for google_news - en kn ta te ml
#  category: for inshorts - national, business, world, technology (leave out for top news)
#
#  Telangana, Andhra Pradesh and Kerala feeds were removed on purpose.
#  Very big news from those states still arrives through the national feeds.
#  Sports is filtered out in the code.
# =====================================================================

sources:
  # ---------- National ----------
  - {name: Google News India, type: google_news, lang: en, section: news, state: IN}
  - {name: Inshorts, type: inshorts, section: news}
  - {name: Inshorts National, type: inshorts, category: national, section: news, state: IN}

  # ---------- Karnataka ----------
  - {name: GN Karnataka, type: google_news, lang: en, query: "Karnataka OR Bengaluru OR Mysuru OR Mangaluru when:1d", section: news, state: KA}
  - {name: GN Kannada, type: google_news, lang: kn, section: news, state: KA}
  - {name: The Hindu Karnataka, type: rss, url: "https://www.thehindu.com/news/national/karnataka/feeder/default.rss", section: news, state: KA}
  - {name: Deccan Herald, type: google_news, lang: en, query: "site:deccanherald.com when:1d", section: news, state: KA}
  - {name: Prajavani, type: google_news, lang: kn, query: "site:prajavani.net when:1d", section: news, state: KA}

  # ---------- Tamil Nadu ----------
  - {name: GN Tamil Nadu, type: google_news, lang: en, query: "\"Tamil Nadu\" OR Chennai OR Coimbatore OR Madurai when:1d", section: news, state: TN}
  - {name: The Hindu Tamil Nadu, type: rss, url: "https://www.thehindu.com/news/national/tamil-nadu/feeder/default.rss", section: news, state: TN}

  # ---------- Tech & Business ----------
  - {name: Inshorts Business, type: inshorts, category: business, section: biz}
  - {name: Inshorts Technology, type: inshorts, category: technology, section: biz}
  - {name: GN Business India, type: google_news, lang: en, query: "(Sensex OR Nifty OR RBI OR GST OR startup OR layoffs OR IPO) India when:1d", section: biz}

  # ---------- International ----------
  - {name: Inshorts World, type: inshorts, category: world, section: news, state: WORLD}
  - {name: GN World, type: google_news, lang: en, query: "world news when:1d", section: news, state: WORLD}

  # ---------- AI (releases and major announcements only) ----------
  - {name: Hacker News, type: hackernews, section: ai}
  - {name: GN AI Launches, type: google_news, lang: en, query: "(OpenAI OR Anthropic OR Google OR Meta OR Microsoft OR Sarvam OR Krutrim) AI (launches OR releases OR unveils OR \"now available\") when:1d", section: ai}
  - {name: OpenAI News, type: rss, url: "https://openai.com/news/rss.xml", section: ai}
  - {name: Google AI Blog, type: rss, url: "https://blog.google/technology/ai/rss/", section: ai}
  - {name: Hugging Face Blog, type: rss, url: "https://huggingface.co/blog/feed.xml", section: ai}

  # ---------- AI Hacks (shown on the page only, not in Telegram) ----------
  - {name: r/ChatGPT, type: reddit, subreddit: ChatGPT, sort: top, section: ai}
  - {name: GN AI Tips, type: google_news, lang: en, query: "(ChatGPT OR Gemini OR Claude) (tips OR tricks OR hack OR prompt) when:2d", section: ai}
