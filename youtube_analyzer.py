"""
youtube_analyzer.py
-------------------
Analisis de rendimiento de canales de YouTube via Data API v3,
y utilidades de gestion de carpetas de proyectos de video.

Funciones exportadas:
  analizar_rendimiento_canal(channel_id)  -> dict | None
  obtener_siguiente_num(ruta_base)        -> int
  obtener_ultimo_video(ruta_base)         -> str | None
"""

import os
import re
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build

from config import YOUTUBE_API_KEY


def analizar_rendimiento_canal(channel_id):
    if not YOUTUBE_API_KEY:
        return None
    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        fecha_limite = (
            (datetime.now(timezone.utc) - timedelta(days=15))
            .isoformat()
            .replace("+00:00", "Z")
        )
        search_res = (
            youtube.search()
            .list(
                part="id",
                channelId=channel_id,
                publishedAfter=fecha_limite,
                type="video",
                maxResults=50,
                order="date",
            )
            .execute()
        )
        video_ids = [item["id"]["videoId"] for item in search_res.get("items", [])]
        if not video_ids:
            return None
        stats_res = (
            youtube.videos()
            .list(part="snippet,statistics", id=",".join(video_ids))
            .execute()
        )
        videos_data = [
            {
                "title": item["snippet"]["title"],
                "views": int(item["statistics"].get("viewCount", 0)),
            }
            for item in stats_res.get("items", [])
        ]
        if not videos_data:
            return None
        avg = sum(video["views"] for video in videos_data) / len(videos_data)
        ganadores = sorted(
            [video for video in videos_data if video["views"] > avg],
            key=lambda video: video["views"],
            reverse=True,
        )
        return {"avg": avg, "ganadores": ganadores}
    except:
        return None


def obtener_siguiente_num(ruta_base):
    if not ruta_base or not os.path.exists(ruta_base):
        return 1
    carpetas = [
        directory
        for directory in os.listdir(ruta_base)
        if os.path.isdir(os.path.join(ruta_base, directory))
    ]
    nums = [
        int(match.group(1))
        for carpeta in carpetas
        if (match := re.search(r"video\s*(\d+)", carpeta, re.IGNORECASE))
    ]
    return max(nums) + 1 if nums else 1


def obtener_ultimo_video(ruta_base):
    """Busca y retorna la ruta de la carpeta del ultimo video generado."""
    if not ruta_base or not os.path.exists(ruta_base):
        return None
    carpetas = [
        directory
        for directory in os.listdir(ruta_base)
        if os.path.isdir(os.path.join(ruta_base, directory))
    ]
    nums = [
        int(match.group(1))
        for carpeta in carpetas
        if (match := re.search(r"video\s*(\d+)", carpeta, re.IGNORECASE))
    ]
    if not nums:
        return None
    return os.path.join(ruta_base, f"video {max(nums)}")