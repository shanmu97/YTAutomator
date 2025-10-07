from pathlib import Path
from typing import List, Dict
import requests


def tts_elevenlabs(api_key: str, text: str, voice_id: str | None, out_path: Path) -> Path:
    voice = voice_id or "21m00Tcm4TlvDq8ikWAM"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream?optimize_streaming_latency=0"
    headers = {
        "xi-api-key": api_key,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.3,
            "use_speaker_boost": True,
        },
        "output_format": "mp3_44100_128",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.post(url, headers=headers, json=payload, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    return out_path


def tts_google(text: str, out_path: Path, language_code: str = "en-US") -> Path:
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(language_code=language_code)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
    response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as out:
        out.write(response.audio_content)
    return out_path


def concatenate_segments_to_audio(segments: List[Dict[str, str]], voice: str, tmp_dir: Path, use_google: bool, api_key: str | None, voice_id: str | None, language: str) -> Path:
    # Join all text for a single TTS pass to keep pacing natural
    text = " ".join([s.get("text", "") for s in segments])
    out_mp3 = tmp_dir / f"voiceover_{voice}.mp3"
    if use_google:
        tts_google(text, out_mp3, language_code=f"{language}-US" if len(language) == 2 else language)
    else:
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY missing and USE_GOOGLE_TTS is false")
        tts_elevenlabs(api_key, text, voice_id, out_mp3)
    return out_mp3
