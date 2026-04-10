"""RSS news fetcher — Stuttgart-focused, with English translation via Groq."""

import os
import time
import xml.etree.ElementTree as ET

import httpx
from dotenv import load_dotenv

load_dotenv()

RSS_FEEDS = [
    "https://www.swr.de/~rss/swraktuell-bw-100.xml",
    "https://www.stuttgarter-zeitung.de/rss/topthemen.rss.feed",
]
CACHE_TTL = 900

STUTTGART_KEYWORDS = {"stuttgart", "cannstatt", "vaihingen", "degerloch", "feuerbach",
                      "zuffenhausen", "möhringen", "botnang", "plieningen", "sillenbuch",
                      "hauptbahnhof", "neckar", "killesberg", "schlossplatz", "königstraße",
                      "s-bahn", "ssb", "vvs"}

_cache: dict = {"items": [], "ts": 0}

FALLBACK_NEWS = [
    {"title": "Stuttgart expands S-Bahn network with new express lines to suburbs", "link": ""},
    {"title": "City council approves €2M road repair budget for Stuttgart-Mitte district", "link": ""},
    {"title": "New cycling lanes open along Neckar river connecting Bad Cannstatt to city center", "link": ""},
    {"title": "Stuttgart ranks among top German cities for urban green space per capita", "link": ""},
    {"title": "Residents call for better street lighting in Zuffenhausen after safety concerns", "link": ""},
]


def _is_stuttgart_relevant(title: str, desc: str = "") -> bool:
    text = (title + " " + desc).lower()
    return any(kw in text for kw in STUTTGART_KEYWORDS)


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


def fetch_news() -> list[dict]:
    """Fetch Stuttgart-relevant RSS headlines, translated to English."""
    now = time.time()
    if _cache["items"] and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["items"]
    for url in RSS_FEEDS:
        try:
            r = httpx.get(url, timeout=5, follow_redirects=True)
            r.raise_for_status()
            root = ET.fromstring(r.text)
            items = []
            for item in root.iter("item"):
                title = item.findtext("title", "").strip()
                desc = item.findtext("description", "").strip()
                link = item.findtext("link", "").strip()
                if title and _is_stuttgart_relevant(title, desc):
                    items.append({"title": title, "link": link})
                if len(items) >= 5:
                    break
            if items:
                items = _translate_headlines(items)
                _cache["items"] = items
                _cache["ts"] = now
                return items
        except Exception:
            continue
    return list(FALLBACK_NEWS)
