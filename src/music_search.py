"""Search for tracks on Yandex Music from a VibeAnalysis."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

from yandex_music import Client
from src.vlm_analyzer import VibeAnalysis

DEFAULT_LIMIT = 10
PLACEHOLDER_ART = "https://placehold.co/300x300/ffcc00/000000?text=Yandex+Music"


@dataclass
class Track:
    name: str
    artist: str
    album_art: str
    url: str
    duration_ms: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


def _build_queries(vibe: VibeAnalysis) -> list[str]:
    queries: list[str] = []

    # 1. Точечный поисковый запрос от VLM
    if vibe.search_query and vibe.search_query.strip():
        queries.append(vibe.search_query.strip())

    # 2. Жанры
    if vibe.genres:
        queries.append(" ".join(vibe.genres[:2]))
        for g in vibe.genres:
            if g.strip():
                queries.append(g.strip())

    # 3. Теги / ключевые слова
    if vibe.keywords:
        for k in vibe.keywords[:3]:
            if k.strip():
                queries.append(k.strip())

    # 4. Фолбэк на короткое описание
    if not queries and vibe.description:
        queries.append(vibe.description.split(".")[0][:50])

    # Дедупликация запросов
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        key = q.lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(q.strip())
    return unique


def _parse_yandex_track(item: Any) -> Track | None:
    track_id = item.id
    name = (item.title or "").strip()
    if not track_id or not name:
        return None

    # Исполнители
    artists = [a.name for a in (item.artists or []) if a.name]
    artist = ", ".join(artists) if artists else "Неизвестный исполнитель"

    # Обложка трека или альбома
    album_art = PLACEHOLDER_ART
    if item.cover_uri:
        album_art = "https://" + item.cover_uri.replace("%%", "300x300")
    elif item.albums and item.albums[0].cover_uri:
        album_art = "https://" + item.albums[0].cover_uri.replace("%%", "300x300")

    # Ссылка на Яндекс Музыку
    album_id = item.albums[0].id if item.albums else 'track'
    url = f"https://music.yandex.ru/album/{album_id}/track/{track_id}"

    duration_ms = int(item.duration_ms or 0)

    return Track(
        name=name,
        artist=artist,
        album_art=album_art,
        url=url,
        duration_ms=duration_ms,
    )


def search_tracks(
    vibe: VibeAnalysis, limit: int | None = None
) -> tuple[list[Track], str | None]:
    """Search Yandex Music for tracks matching the given vibe."""
    max_results = limit
    if max_results is None:
        max_results = int(os.getenv("PLAYLIST_TRACK_LIMIT", DEFAULT_LIMIT))
    max_results = max(1, min(50, max_results))

    token = os.getenv("YANDEX_MUSIC_TOKEN")

    # Инициализация клиента (с поддержкой фолбэка на анонимный вход)
    try:
        if token:
            client = Client(token).init()
        else:
            client = Client().init()
    except Exception:
        try:
            client = Client().init()
        except Exception as exc:
            return [], f"Ошибка подключения к Яндекс Музыке: {exc}"

    queries = _build_queries(vibe)
    tracks: list[Track] = []
    seen_ids: set[str] = set()

    try:
        for query in queries:
            if len(tracks) >= max_results:
                break

            search_result = client.search(text=query, type_="track")
            if not search_result or not search_result.tracks:
                continue

            items = search_result.tracks.results or []
            for item in items:
                track_id = str(item.id)
                if track_id in seen_ids:
                    continue

                track = _parse_yandex_track(item)
                if track:
                    seen_ids.add(track_id)
                    tracks.append(track)
                    if len(tracks) >= max_results:
                        break
    except Exception as exc:
        return [], f"Сетевая ошибка или сбой API Яндекс Музыки: {exc}"

    if not tracks:
        return [], "Треки не найдены. Попробуйте сгенерировать заново."

    return tracks, None