"""
YouTube → Vertical Short Generator
Converts any YouTube video into a 9:16 short with AI voiceover and captions.
"""

import streamlit as st
import tempfile
import os
import asyncio
import textwrap
import subprocess
import json
import re
from pathlib import Path

st.set_page_config(
    page_title="YT → Short Generator",
    page_icon="🎬",
    layout="centered",
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  .stApp { background: #0d0d0f; color: #e8e8ea; }
  .hero { text-align: center; padding: 2.5rem 1rem 1.5rem; border-bottom: 1px solid #1e1e22; margin-bottom: 2rem; }
  .hero h1 { font-size: 2rem; font-weight: 700; color: #ffffff; margin: 0; letter-spacing: -0.5px; }
  .hero p  { color: #888; font-size: 0.95rem; margin: 0.4rem 0 0; }
  .section-label { font-size: 0.75rem; font-weight: 600; letter-spacing: 0.06em; color: #666; text-transform: uppercase; margin-bottom: 0.6rem; }
  .stTextInput > div > div > input { background: #0d0d0f !important; border: 1px solid #2e2e36 !important; border-radius: 8px !important; color: #e8e8ea !important; font-size: 0.95rem !important; }
  .stTextInput > div > div > input:focus { border-color: #6c63ff !important; box-shadow: 0 0 0 2px rgba(108,99,255,0.25) !important; }
  .stSelectbox > div > div { background: #0d0d0f !important; border: 1px solid #2e2e36 !important; border-radius: 8px !important; color: #e8e8ea !important; }
  .stButton > button { width: 100%; background: #6c63ff; color: #ffffff; border: none; border-radius: 8px; padding: 0.75rem; font-size: 1rem; font-weight: 600; cursor: pointer; transition: opacity 0.15s; }
  .stButton > button:hover { opacity: 0.88; }
  .stDownloadButton > button { width: 100%; background: #22c55e; color: #ffffff; border: none; border-radius: 8px; padding: 0.75rem; font-size: 1rem; font-weight: 600; }
  .stSpinner > div { border-top-color: #6c63ff !important; }
  .stAlert { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <h1>🎬 YouTube → Short</h1>
  <p>Paste a link. Get a vertical short with voiceover &amp; captions.</p>
</div>
""", unsafe_allow_html=True)


def validate_youtube_url(url: str) -> bool:
    pattern = re.compile(
        r"(https?://)?(www\.)?"
        r"(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)"
        r"[\w\-]{11}"
    )
    return bool(pattern.search(url))


def get_video_info(url: str) -> dict:
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-playlist",
        "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "--add-header", "Accept-Language:en-US,en;q=0.9",
        "--extractor-args", "youtube:player_client=web,mweb",
        "--no-check-certificates",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp metadata error: {result.stderr[:300]}")
    return json.loads(result.stdout)


def download_video_segment(url: str, out_path: str, start: int, duration: int) -> None:
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]",
        "--merge-output-format", "mp4",
        "--download-sections", f"*{start}-{start + duration}",
        "--force-keyframes-at-cuts",
        "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "--add-header", "Accept-Language:en-US,en;q=0.9",
        "--extractor-args", "youtube:player_client=web,mweb",
        "--no-check-certificates",
        "--retries", "5",
        "--fragment-retries", "5",
        "-o", out_path,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"Download failed:\n{result.stderr[:500]}")


def generate_script(title: str, description: str, style: str, duration: int) -> str:
    max_words = int(duration * 150 / 60 * 0.90)
    intros = {
        "energetic":  "You NEED to see this.",
        "calm":       "Here's something worth knowing.",
        "educational":"Let's break this down quickly.",
        "hype":       "This is absolutely insane — watch.",
    }
    outros = {
        "energetic":  "Drop a comment if this blew your mind!",
        "calm":       "Hope that was helpful. See you next time.",
        "educational":"Follow for more breakdowns like this.",
        "hype":       "Like and share — you won't regret it!",
    }
    desc_snippet = (description or "")[:400].strip()
    body = desc_snippet if desc_snippet else title
    full = f"{intros[style]} {title}. {body} {outros[style]}"
    words = full.split()
    if len(words) > max_words:
        words = words[:max_words - 4]
        words.append(outros[style])
    return " ".join(words)


async def _tts_async(script: str, voice: str, audio_path: str) -> None:
    import edge_tts
    communicate = edge_tts.Communicate(script, voice)
    await communicate.save(audio_path)


def generate_voiceover(script: str, voice: str, audio_path: str) -> None:
    asyncio.run(_tts_async(script, voice, audio_path))


def get_audio_duration(audio_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return float(result.stdout.strip())


def build_caption_filter(script: str, audio_dur: float) -> str:
    wrapped = textwrap.fill(script, width=35)
    safe = (
        wrapped
        .replace("\\", "\\\\")
        .replace("'", "\u2019")
        .replace(":", "\\:")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )
    return (
        f"drawtext=text='{safe}'"
        f":fontsize=38"
        f":fontcolor=white"
        f":bordercolor=black:borderw=3"
        f":x=(w-text_w)/2"
        f":y=h-th-120"
        f":font='DejaVu Sans'"
        f":enable='between(t,0,{audio_dur:.1f})'"
    )


def compose_short(
    raw_video: str,
    audio_path: str,
    script: str,
    out_path: str,
    target_w: int = 1080,
    target_h: int = 1920,
) -> None:
    audio_dur = get_audio_duration(audio_path)
    caption_filter = build_caption_filter(script, audio_dur)
    video_filter = (
        f"crop=ih*9/16:ih,"
        f"scale={target_w}:{target_h},"
        f"{caption_filter}"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", raw_video,
        "-i", audio_path,
        "-t", str(audio_dur),
        "-filter_complex", f"[0:v]{video_filter}[vout]",
        "-map", "[vout]",
        "-map", "1:a",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "26",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg compose failed:\n{result.stderr[-600:]}")


# ── UI ─────────────────────────────────────────────────────────────────────────

with st.container():
    st.markdown('<div class="section-label">YouTube URL</div>', unsafe_allow_html=True)
    yt_url = st.text_input(
        label="YouTube URL",
        placeholder="https://www.youtube.com/watch?v=...",
        label_visibility="collapsed",
    )

col1, col2 = st.columns(2)
with col1:
    st.markdown('<div class="section-label">Clip start (seconds)</div>', unsafe_allow_html=True)
    clip_start = st.number_input("Start", min_value=0, value=0, step=5, label_visibility="collapsed")

with col2:
    st.markdown('<div class="section-label">Clip duration (seconds)</div>', unsafe_allow_html=True)
    clip_duration = st.slider("Duration", min_value=15, max_value=60, value=30, step=5, label_visibility="collapsed")

col3, col4 = st.columns(2)
with col3:
    st.markdown('<div class="section-label">Script style</div>', unsafe_allow_html=True)
    style = st.selectbox(
        "Style",
        ["energetic", "calm", "educational", "hype"],
        label_visibility="collapsed",
    )

with col4:
    st.markdown('<div class="section-label">Narrator voice</div>', unsafe_allow_html=True)
    VOICE_MAP = {
        "Aria (US Female)": "en-US-AriaNeural",
        "Guy (US Male)": "en-US-GuyNeural",
        "Jenny (US Female)": "en-US-JennyNeural",
        "Ryan (UK Male)": "en-GB-RyanNeural",
        "Sonia (UK Female)": "en-GB-SoniaNeural",
    }
    voice = st.selectbox(
        "Voice",
        list(VOICE_MAP.keys()),
        label_visibility="collapsed",
    )
    voice_id = VOICE_MAP[voice]

with st.expander("✏️  Override script (optional)"):
    custom_script = st.text_area(
        "Write your own narration script (leave blank to auto-generate):",
        height=120,
        placeholder="The world's greatest discovery happened by accident...",
    )

st.markdown("---")

# ── Generate ───────────────────────────────────────────────────────────────────

if st.button("⚡  Generate Short"):

    if not yt_url.strip():
        st.error("Please paste a YouTube URL above.")
        st.stop()

    if not validate_youtube_url(yt_url.strip()):
        st.error("That doesn't look like a valid YouTube URL. Check the link and try again.")
        st.stop()

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_video   = os.path.join(tmpdir, "raw.mp4")
        audio_file  = os.path.join(tmpdir, "voice.mp3")
        output_file = os.path.join(tmpdir, "short.mp4")

        progress = st.progress(0)
        status   = st.empty()

        try:
            status.info("🔍 Fetching video info…")
            info = get_video_info(yt_url.strip())
            title       = info.get("title", "Untitled")
            description = info.get("description", "")
            progress.progress(10)
            st.caption(f"**Found:** {title}")

            status.info("✍️  Generating script…")
            script = custom_script.strip() if custom_script.strip() else generate_script(
                title, description, style, clip_duration
            )
            progress.progress(20)

            with st.expander("📄 Script preview"):
                st.write(script)

            status.info("🎙️  Generating voiceover with Edge-TTS…")
            generate_voiceover(script, voice_id, audio_file)
            progress.progress(45)

            status.info("⬇️  Downloading video segment…")
            download_video_segment(yt_url.strip(), raw_video, int(clip_start), clip_duration)
            progress.progress(70)

            status.info("🎞️  Composing vertical short…")
            compose_short(raw_video, audio_file, script, output_file)
            progress.progress(95)

            status.empty()
            progress.progress(100)
            st.success("✅ Your short is ready!")

            with open(output_file, "rb") as f:
                video_bytes = f.read()

            st.video(video_bytes)

            safe_title = re.sub(r"[^\w\s-]", "", title)[:40].strip().replace(" ", "_")
            st.download_button(
                label="⬇️  Download MP4",
                data=video_bytes,
                file_name=f"{safe_title}_short.mp4",
                mime="video/mp4",
            )

        except RuntimeError as e:
            progress.empty()
            status.empty()
            st.error(f"Something went wrong:\n\n```\n{e}\n```")

        except Exception as e:
            progress.empty()
            status.empty()
            st.error(f"Unexpected error: {e}")

st.markdown("""
<hr style="border-color:#1e1e22; margin-top:2rem;">
<p style="text-align:center; color:#444; font-size:0.8rem;">
  Powered by yt-dlp · Edge-TTS · FFmpeg &nbsp;|&nbsp; Personal use only.
</p>
""", unsafe_allow_html=True)
