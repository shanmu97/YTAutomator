import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    timezone: str
    video_width: int
    video_height: int
    fps: int
    max_duration_seconds: int
    language: str
    topic_category: str
    topic_seed: str | None
    content_style: str
    use_google_tts: bool
    voice_id: str | None
    hashtags_count: int

    gemini_api_key: str | None
    elevenlabs_api_key: str | None
    pexels_api_key: str | None
    youtube_channel_id: str | None


def get_config() -> AppConfig:
    return AppConfig(
        timezone=os.getenv("TIMEZONE", "America/New_York"),
        video_width=int(os.getenv("VIDEO_WIDTH", "1080")),
        video_height=int(os.getenv("VIDEO_HEIGHT", "1920")),
        fps=int(os.getenv("FPS", "30")),
        max_duration_seconds=int(os.getenv("MAX_DURATION_SECONDS", "60")),
        language=os.getenv("LANGUAGE", "en"),
        topic_category=os.getenv("TOPIC_CATEGORY", "technology"),
        topic_seed=os.getenv("TOPIC_SEED") or None,
        content_style=os.getenv("CONTENT_STYLE", "default"),
        use_google_tts=os.getenv("USE_GOOGLE_TTS", "false").lower() == "true",
        voice_id=os.getenv("VOICE_ID") or None,
        hashtags_count=int(os.getenv("HASHTAGS_COUNT", "6")),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY"),
        pexels_api_key=os.getenv("PEXELS_API_KEY"),
        youtube_channel_id=os.getenv("YOUTUBE_CHANNEL_ID"),
    )
