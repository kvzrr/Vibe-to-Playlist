"""Analyze an image via OpenRouter / OpenAI API and extract playlist metadata."""

from __future__ import annotations

import base64
import io
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

load_dotenv()

# Актуальная модель Gemini 3.6 Flash в OpenRouter
DEFAULT_MODEL = os.getenv("VLM_MODEL", "google/gemini-3.6-flash")

SYSTEM_PROMPT = """You analyze images for music playlist curation.
Respond with a single valid JSON object only. Do not use markdown blocks.
JSON schema:
{
  "description": "atmospheric mood of the photo in Russian, 2-3 short sentences",
  "genres": ["genre1", "genre2"],
  "keywords": ["word1", "word2", "word3"],
  "search_query": "one optimized line for Spotify track search in English"
}
"""


@dataclass
class VibeAnalysis:
    description: str
    genres: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    search_query: str = ""

    def to_markdown(self) -> str:
        genres = ", ".join(self.genres) if self.genres else "—"
        keywords = ", ".join(self.keywords) if self.keywords else "—"
        return (
            "### Настроение фото\n\n"
            f"{self.description}\n\n"
            f"**Жанры:** {genres}\n\n"
            f"**Keywords:** {keywords}\n\n"
            f"**Spotify query:** `{self.search_query}`"
        )


class VlmAnalyzerError(RuntimeError):
    pass


def strip_llm_json(raw: str) -> str:
    """Remove markdown fences and isolate a JSON object from model output."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    obj_match = re.search(r"\{[\s\S]*\}", text)
    if obj_match:
        return obj_match.group(0).strip()
    return text


def _encode_image(image: Image.Image) -> tuple[str, str]:
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    return "image/jpeg", b64


def _clamp_list(values: list[str], *, min_len: int, max_len: int) -> list[str]:
    cleaned = [v.strip() for v in values if v and str(v).strip()]
    if len(cleaned) >= min_len:
        return cleaned[:max_len]
    return cleaned


def _parse_vibe_payload(raw: str) -> VibeAnalysis:
    text = strip_llm_json(raw)
    data: dict[str, Any] = {}
    
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Если JSON обрезался, пробуем вытащить данные регулярками перед падением
        desc_match = re.search(r'"description"\s*:\s*"([^"]*)', text)
        query_match = re.search(r'"search_query"\s*:\s*"([^"]*)', text)
        
        data = {
            "description": desc_match.group(1) if desc_match else "Атмосферный снимок.",
            "genres": ["ambient", "chill"],
            "keywords": ["vibes", "mood"],
            "search_query": query_match.group(1) if query_match else "chill ambient",
        }

    description = str(data.get("description", "")).strip() or "Спокойная, нейтральная атмосфера на снимке."
    genres = _clamp_list([str(g) for g in data.get("genres") or []], min_len=1, max_len=3)
    keywords = _clamp_list([str(k) for k in data.get("keywords") or []], min_len=1, max_len=5)

    search_query = str(data.get("search_query", "")).strip()
    if not search_query:
        search_query = " ".join(genres[:2] + keywords[:3]).strip() or "chill ambient"

    return VibeAnalysis(
        description=description,
        genres=genres,
        keywords=keywords,
        search_query=search_query,
    )


def analyze_image(image: Image.Image, *, model: str | None = None) -> VibeAnalysis:
    """Analyze image using OpenRouter / OpenAI API."""
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if openrouter_key:
        client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")
        selected_model = model or DEFAULT_MODEL
    elif openai_key:
        client = OpenAI(api_key=openai_key)
        selected_model = model or "gpt-4o-mini"
    else:
        raise VlmAnalyzerError(
            "Не найден API ключ! Укажите OPENROUTER_API_KEY или OPENAI_API_KEY в .env файле."
        )

    mime, b64 = _encode_image(image)

    try:
        response = client.chat.completions.create(
            model=selected_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Проанализируй атмосферу изображения и подбери музыку. Ответ — строго JSON.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                    ],
                },
            ],
            max_tokens=1200,
            temperature=0.35,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise VlmAnalyzerError("Получен пустой ответ от модели.")
        return _parse_vibe_payload(content)
    except Exception as exc:
        raise VlmAnalyzerError(f"Ошибка вызова VLM API: {exc}") from exc


# =====================================================================
# Совместимость с app.py
# =====================================================================

def analyze_vibe(image: Image.Image) -> VibeAnalysis:
    return analyze_image(image)


def extract_music_tags(vibe: VibeAnalysis | str) -> dict[str, Any]:
    if isinstance(vibe, VibeAnalysis):
        return {
            "description": vibe.description,
            "genres": vibe.genres,
            "keywords": vibe.keywords,
            "search_query": vibe.search_query,
        }
    return {
        "description": str(vibe),
        "genres": [],
        "keywords": [],
        "search_query": str(vibe),
    }