from pathlib import Path
import requests
from typing import List


def search_pexels_videos(api_key: str, query: str, per_page: int = 3) -> List[str]:
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": per_page, "orientation": "portrait"}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    urls: List[str] = []
    for v in data.get("videos", [])[:per_page]:
        files = v.get("video_files", [])
        portrait = [f for f in files if f.get("height", 0) > f.get("width", 0)]
        best = sorted(portrait or files, key=lambda f: f.get("width", 0) * f.get("height", 0), reverse=True)
        if best:
            urls.append(best[0]["link"])
    return urls


def search_pexels_photos(api_key: str, query: str, per_page: int = 5) -> List[str]:
    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": per_page, "orientation": "portrait"}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    urls: List[str] = []
    for p in data.get("photos", [])[:per_page]:
        src = p.get("src", {})
        # Prefer large portrait-friendly
        link = src.get("large2x") or src.get("large") or src.get("original")
        if link:
            urls.append(link)
    return urls


def download_files(urls: List[str], out_dir: Path) -> List[Path]:
    paths: List[Path] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, url in enumerate(urls):
        ext = ".mp4" if ".mp4" in url.lower() else (".jpg" if any(x in url.lower() for x in [".jpg", ".jpeg"]) else ".png")
        p = out_dir / f"asset_{i}{ext}"
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(p, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        paths.append(p)
    return paths
