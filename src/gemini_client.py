from typing import Dict, List
import google.generativeai as genai
import datetime


SYSTEM_PROMPT = (
    "You generate compelling, concise YouTube Shorts scripts under 55 seconds "
    "with strong hooks, 3-5 punchy facts, and a crisp CTA."
)

SCIENCE_FACT_PROMPT = (
    "You are a science explainer. Create a short (30–60s), surprising, accurate script "
    "for a general audience. Use a catchy opening hook, 4–6 concise lines, and a memorable wrap-up. "
    "Avoid fiction and morals; stick to real science facts (space, physics, nature, animals, inventions, history of science)."
)

DEFAULT_MODELS: List[str] = [
    "gemini-2.5-flash"
]


def init_gemini(api_key: str | None):
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    genai.configure(api_key=api_key)


def _get_model():
    last_err = None
    for name in DEFAULT_MODELS:
        try:
            model = genai.GenerativeModel(name)
            return model
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"No Gemini model available. Last error: {last_err}")


def pick_topic_from_seed(seed: str, language: str) -> str:
    model = _get_model()
    prompt = (
        f"Create a concise YouTube Shorts topic inspired by this theme: '{seed}'. "
        f"Keep it specific and catchy, under 10 words, in {language}. Return only the topic text."
    )
    resp = model.generate_content(prompt)
    topic = (resp.text or seed).strip().split("\n")[0]
    return topic


def pick_trending_topic(category: str, language: str) -> str:
    model = _get_model()
    today = datetime.date.today().isoformat()
    prompt = (
        f"List 5 trending, evergreen-friendly short topics in {category} for YouTube Shorts "
        f"today ({today}) in {language}. Return only one best topic." 
    )
    resp = model.generate_content(prompt)
    topic = resp.text.strip().split("\n")[0]
    return topic


def generate_script(topic: str, language: str, content_style: str = "default") -> Dict[str, List[Dict[str, str]]]:
    model = _get_model()
    style_prompt = SYSTEM_PROMPT

    prompt = (
        f"{style_prompt}\n\n"
        f"Topic: {topic}\nLanguage: {language}\n"
        "Write a script as 6-10 short lines. Each line under 12 words."
        " Start with a catchy hook, include surprising facts, and end memorably."
        " Reply as JSON with an array 'segments', each having 'text'."
    )
    resp = model.generate_content(prompt)
    text = resp.text
    import json, re
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        lines = [l.strip("- ") for l in text.splitlines() if l.strip()]
        segments = [{"text": l} for l in lines[:10]]
        return {"segments": segments}
    try:
        data = json.loads(match.group(0))
        return data
    except Exception:
        lines = [l.strip("- ") for l in text.splitlines() if l.strip()]
        segments = [{"text": l} for l in lines[:10]]
        return {"segments": segments}


def generate_hashtags(topic: str, language: str, content_style: str, max_count: int) -> List[str]:
    model = _get_model()
    prompt = (
        f"Generate up to {max_count} short, trending-style hashtags for a YouTube Short.\n"
        f"Topic: {topic}\nLanguage: {language}\nStyle: {content_style}\n"
        "Rules: Only hashtags, no explanations. Prefer general but relevant tags."
    )
    resp = model.generate_content(prompt)
    tags = []
    for raw in (resp.text or "").split():
        tag = raw.strip().strip(",.;")
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = "#" + tag
        tags.append(tag)
    # de-dup and cap
    seen = set()
    out: List[str] = []
    for t in tags:
        k = t.lower()
        if k not in seen:
            out.append(t)
            seen.add(k)
        if len(out) >= max_count:
            break
    return out
