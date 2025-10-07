from __future__ import annotations
from pathlib import Path
from datetime import datetime
import re

from src.config import get_config
from src.gemini_client import init_gemini, pick_trending_topic, generate_script, pick_topic_from_seed, generate_hashtags
from src.pexels_client import search_pexels_videos, search_pexels_photos, download_files
from src.tts import concatenate_segments_to_audio
from src.video_creator import create_video_with_subtitles
from src.youtube_client import get_youtube_service, upload_short


OUTPUT_DIR = Path("output")


_DOMAIN_KEYWORDS = {
    "space": ["space", "cosmos", "galaxy", "star", "nebula", "planet", "astronomy", "nasa", "universe"],
    "ocean": ["ocean", "sea", "deep sea", "marine", "jellyfish", "coral", "bioluminescent", "fish"],
    "earth": ["volcano", "earthquake", "weather", "storm", "lightning", "desert", "forest", "mountain", "earth"],
    "animals": ["animal", "tiger", "elephant", "bird", "insect", "mammal", "wildlife"],
    "physics": ["physics", "quantum", "particle", "magnet", "light", "gravity", "relativity"],
    "inventions": ["invention", "engine", "machine", "robot", "technology", "device", "history of science"],
}


def _detect_domain(topic: str, segments: list[dict[str, str]], content_style: str) -> tuple[str, list[str]]:
    text = (topic + "\n" + "\n".join(s.get("text", "") for s in segments)).lower()
    for domain, keys in _DOMAIN_KEYWORDS.items():
        if any(k in text for k in keys):
            return domain, keys
    # default based on style
    if content_style == "science_fact":
        return "science", ["science", "infographic", "macro"]
    return "generic", ["abstract", "minimal"]


def _candidate_queries(topic: str, domain: str) -> list[str]:
    topic_simple = re.sub(r"[^a-z0-9\s]", "", topic.lower()).strip()
    seeds = {
        "space": [
            f"{topic_simple} space galaxy stars nebula night sky",
            "cosmos galaxy nebula starfield space",
            "planet earth nasa astronomy space",
        ],
        "ocean": [
            f"{topic_simple} ocean sea deep sea marine",
            "bioluminescent ocean jellyfish marine",
            "coral reef underwater ocean",
        ],
        "earth": [
            f"{topic_simple} volcano storm lightning nature",
            "desert forest mountain nature",
            "time lapse clouds sky",
        ],
        "animals": [
            f"{topic_simple} wildlife animal macro",
            "wildlife closeup animal nature",
            "bird mammal insect macro",
        ],
        "physics": [
            f"{topic_simple} physics particles light energy",
            "quantum abstract particles light",
            "magnet gravity waves",
        ],
        "inventions": [
            f"{topic_simple} invention technology device",
            "gears machine engineering",
            "robot circuit board technology",
        ],
        "science": [
            f"{topic_simple} science infographic macro",
            "microscope cells macro science",
            "abstract science background",
        ],
        "generic": [
            topic_simple,
            f"{topic_simple} abstract",
        ],
    }
    return seeds.get(domain, seeds["generic"])


def run_pipeline_once():
    cfg = get_config()

    job_dir = OUTPUT_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
    assets_dir = job_dir / "assets"
    tmp_dir = job_dir / "tmp"
    job_dir.mkdir(parents=True, exist_ok=True)

    init_gemini(cfg.gemini_api_key)

    if cfg.topic_seed:
        topic = pick_topic_from_seed(cfg.topic_seed, cfg.language)
    else:
        topic = pick_trending_topic(cfg.topic_category, cfg.language)

    script = generate_script(topic, cfg.language, content_style=cfg.content_style)
    segments = script.get("segments", [])

    # Improved media selection: detect domain and iterate multiple queries until found
    domain, _ = _detect_domain(topic, segments, cfg.content_style)
    queries = _candidate_queries(topic, domain)

    video_urls: list[str] = []
    image_urls: list[str] = []
    if cfg.pexels_api_key:
        for q in queries:
            if not video_urls:
                vs = search_pexels_videos(cfg.pexels_api_key, query=q, per_page=3)
                video_urls.extend(vs)
            if not video_urls and not image_urls:
                is_ = search_pexels_photos(cfg.pexels_api_key, query=q, per_page=6)
                image_urls.extend(is_)
            if video_urls or image_urls:
                break

    asset_urls = video_urls or image_urls
    assets = download_files(asset_urls, assets_dir) if asset_urls else []

    voiceover_path = concatenate_segments_to_audio(
        segments=segments,
        voice="narrator",
        tmp_dir=tmp_dir,
        use_google=cfg.use_google_tts,
        api_key=cfg.elevenlabs_api_key,
        voice_id=cfg.voice_id,
        language=cfg.language,
    )

    out_video = job_dir / "short.mp4"
    create_video_with_subtitles(
        assets=assets,
        voiceover=voiceover_path,
        segments=segments,
        width=cfg.video_width,
        height=cfg.video_height,
        fps=cfg.fps,
        max_duration=cfg.max_duration_seconds,
        out_path=out_video,
    )

    hashtags = generate_hashtags(topic, cfg.language, cfg.content_style, cfg.hashtags_count)

    youtube = get_youtube_service()
    title = f"{topic} #Shorts"
    description = "Auto-generated short using AI.\n" + (" ".join(hashtags) if hashtags else "")
    video_id = upload_short(youtube, out_video, title=title, description=description, tags=["shorts", cfg.topic_category, cfg.content_style])

    print(f"Uploaded video: https://youtube.com/shorts/{video_id}")
