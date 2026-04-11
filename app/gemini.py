"""AI image classification via Groq (Llama 4 Scout vision)."""

import base64
import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

VALID_CATEGORIES = {"pothole", "streetlight", "graffiti", "flooding", "dumping", "sign", "other"}
VALID_SEVERITIES = {"low", "medium", "high", "critical"}
VALID_DEPARTMENTS = {"roads", "electrical", "sanitation", "water", "parks", "general"}

FALLBACK = {
    "category": "unclassified",
    "severity": "medium",
    "department": "general",
    "description": "Classification pending \u2014 AI service unavailable",
}

PROMPT = (
    "You are an urban infrastructure analyst. Analyze this photo of a reported city issue.\n\n"
    "Respond in JSON only:\n"
    "{\n"
    '  "category": one of ["pothole", "streetlight", "graffiti", "flooding", "dumping", "sign", "other"],\n'
    '  "severity": one of ["low", "medium", "high", "critical"],\n'
    '  "department": one of ["roads", "electrical", "sanitation", "water", "parks", "general"],\n'
    '  "description": "One sentence describing the issue"\n'
    "}"
)


def _detect_mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def parse_gemini_response(text: str) -> dict:
    """Parse and validate AI response text. Returns FALLBACK on any issue."""
    try:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            first_nl = cleaned.index("\n")
            cleaned = cleaned[first_nl + 1:]
            cleaned = cleaned[:cleaned.rindex("```")].strip()
        data = json.loads(cleaned)
        if (
            data.get("category") not in VALID_CATEGORIES
            or data.get("severity") not in VALID_SEVERITIES
            or data.get("department") not in VALID_DEPARTMENTS
            or not isinstance(data.get("description"), str)
            or not data["description"].strip()
        ):
            return dict(FALLBACK)
        return {
            "category": data["category"],
            "severity": data["severity"],
            "department": data["department"],
            "description": data["description"],
        }
    except Exception:
        return dict(FALLBACK)


async def classify_image(image_bytes: bytes) -> dict:
    """Classify image using Groq Llama 4 Scout. Returns FALLBACK on any failure."""
    try:
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            return dict(FALLBACK)
        mime = _detect_mime(image_bytes)
        b64 = base64.b64encode(image_bytes).decode()
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json={
                    "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                    "messages": [{"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        {"type": "text", "text": PROMPT},
                    ]}],
                    "max_tokens": 200,
                },
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=30,
            )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        return parse_gemini_response(text)
    except Exception:
        return dict(FALLBACK)
