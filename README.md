## YouTube Shorts Auto-Generator

Generates and uploads 3 YouTube Shorts daily (9:00, 14:00, 19:00 local time):
- Select trending topic
- Generate script (Gemini)
- Generate voiceover (ElevenLabs or Google TTS)
- Assemble 9:16 video with visuals + burnt-in subtitles (MoviePy)
- Upload to YouTube (YouTube Data API)

### Quickstart

1) Python 3.10+
2) Install dependencies:
```bash
pip install -r requirements.txt
```
3) Create `.env` from example and fill values:
```bash
copy .env.example .env
```
4) Provide Google OAuth credentials for YouTube upload:
- Create a Desktop app OAuth client in Google Cloud Console
- Download `client_secret.json` into the project root
- First run will open a browser for consent and store a token file (e.g. `token.json`)

5) Run once:
```bash
python main.py --run-once
```

6) Run scheduler (APScheduler, runs 9:00, 14:00, 19:00 daily):
```bash
python main.py
```

### Environment (.env)
- `GEMINI_API_KEY` — for Gemini
- `ELEVENLABS_API_KEY` — for ElevenLabs (optional if using Google TTS)
- `PEXELS_API_KEY` — for stock media
- `YOUTUBE_CHANNEL_ID` — uploads target channel (optional; inferred from auth)
- `TIMEZONE` — e.g. `America/New_York`
- `USE_GOOGLE_TTS` — set to `true` to use Google Cloud TTS instead of ElevenLabs
- `GOOGLE_APPLICATION_CREDENTIALS` — if using Google TTS

### Windows Task Scheduler (alternative to APScheduler)
If you prefer not to keep a Python process running, create three Windows Task Scheduler tasks to run:
```bash
python main.py --run-once
```
At 09:00, 14:00, and 19:00 daily. Ensure the working directory is the project root.

### Notes
- Outputs are written to `output/` with timestamped folders per job.
- MoviePy uses FFMPEG under the hood; install FFMPEG if not present.
- This repo supports both ElevenLabs and Google TTS; set flags accordingly.
