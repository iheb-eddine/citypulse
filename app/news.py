"""RSS news fetcher — city-aware, with English translation via Groq."""

import os
import time
import xml.etree.ElementTree as ET

import httpx
from dotenv import load_dotenv

load_dotenv()

CACHE_TTL = 900

_cache: dict = {}

FALLBACK_NEWS = {
    "stuttgart": [
        {"title": "Stuttgart expands S-Bahn network with new express lines to suburbs", "link": ""},
        {"title": "City council approves €2M road repair budget for Stuttgart-Mitte district", "link": ""},
        {"title": "New cycling lanes open along Neckar river connecting Bad Cannstatt to city center", "link": ""},
        {"title": "Stuttgart ranks among top German cities for urban green space per capita", "link": ""},
        {"title": "Residents call for better street lighting in Zuffenhausen after safety concerns", "link": ""},
    ],
}


def _is_relevant(title: str, desc: str, keywords: set) -> bool:
    text = (title + " " + desc).lower()
    return any(kw in text for kw in keywords)


def _translate_headlines(headlines: list[dict]) -> list[dict]:
    """Translate German headlines to English via Groq."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key or not headlines:
        return headlines
    titles = "\n".join(f"- {h['title']}" for h in headlines)
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "system", "content": "Translate each German headline to English. Keep the same format (one per line starting with -). Only output the translated lines, nothing else."},
                    {"role": "user", "content": titles},
                ],
                "max_tokens": 300,
            },
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=8,
        )
        r.raise_for_status()
        translated = r.json()["choices"][0]["message"]["content"].strip().split("\n")
        result = []
        for i, line in enumerate(translated):
            title = line.lstrip("- ").strip()
            if title and i < len(headlines):
                result.append({"title": title, "link": headlines[i].get("link", "")})
        return result if result else headlines
    except Exception:
        return headlines


def fetch_news(city_key: str = "stuttgart") -> list[dict]:
    """Fetch city-relevant RSS headlines, translated to English."""
    from app.main import CITIES, DEFAULT_CITY
    city_cfg = CITIES.get(city_key, CITIES[DEFAULT_CITY])
    keywords = city_cfg.get("news_keywords", set())
    feeds = city_cfg.get("rss_feeds", [])

    now = time.time()
    cached = _cache.get(city_key)
    if cached and (now - cached["ts"]) < CACHE_TTL:
        return cached["items"]

    for url in feeds:
        try:
            r = httpx.get(url, timeout=5, follow_redirects=True)
            r.raise_for_status()
            root = ET.fromstring(r.text)
            items = []
            for item in root.iter("item"):
                title = item.findtext("title", "").strip()
                desc = item.findtext("description", "").strip()
                link = item.findtext("link", "").strip()
                if title and _is_relevant(title, desc, keywords):
                    items.append({"title": title, "link": link})
                if len(items) >= 5:
                    break
            if items:
                items = _translate_headlines(items)
                _cache[city_key] = {"items": items, "ts": now}
                return items
        except Exception:
            continue
    return list(FALLBACK_NEWS.get(city_key, []))
