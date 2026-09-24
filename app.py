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

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="YT → Short Generator",
    page_icon="🎬",
    layout="centered",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Import a clean, modern font */
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

  /* Dark cinematic background */
  .stApp { background: #0d0d0f; color: #e8e8ea; }

  /* Header strip */
  .hero {
    text-align: center;
    padding: 2.5rem 1rem 1.5rem;
    border-bottom: 1px solid #1e1e22;
    margin-bottom: 2rem;
  }
  .hero h1 { font-size: 2rem; font-weight: 700; color: #ffffff; margin: 0; letter-spacing: -0.5px; }
  .hero p  { color: #888; font-size: 0.95rem; margin: 0.4rem 0 0; }

  /* Card wrapper */
  .card {
    background: #16161a;
    border: 1px solid #26262c;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.25rem;
  }

  /* Section labels */
  .section-label {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    color: #666;
    text-transform: uppercase;
    margin-bottom: 0.6rem;
  }

  /* Override Streamlit input borders */
  .stTextInput > div > div > input {
    background: #0d0d0f !important;
    border: 1px solid #2e2e36 !important;
    border-radius: 8px !important;
    color: #e8e8ea !important;
    font-size: 0.95rem !important;
  }
  .stTextInput > div > div > input:focus {
    border-color: #6c63ff !important;
    box-shadow: 0 0 0 2px rgba(108,99,255,0.25) !important;
  }

  /* Selectbox */
  .stSelectbox > div > div {
    background: #0d0d0f !important;
    border: 1px solid #2e2e36 !important;
    border-radius: 8px !important;
    color: #e8e8ea !important;
  }

  /* Slider accent */
  .stSlider [data-baseweb="slider"] [role="slider"] { background: #6c63ff; }

  /* Generate button */
  .stButton > button {
    width: 100%;
    background: #6c63ff;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 0.75rem;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .stButton > button:hover { opacity: 0.88; }

  /* Download button */
  .stDownloadButton > button {
    width: 100%;
    background: #22c55e;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 0.75rem;
    font-size: 1rem;
    font-weight: 600;
  }

  /* Progress / spinner tweaks */
  .stSpinner > div { border-top-color: #6c63ff !important; }

  /* Info / success / error boxes */
  .stAlert { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ── Hero header ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <h1>🎬 YouTube → Short</h1>
  <p>Paste a link. Get a vertical short with voiceover &amp; captions.</p>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Helper utilities
# ══════════════════════════════════════════════════════════════════════════════

def validate_youtube_url(url: str) -> bool:
    """Return True if the URL looks like a valid YouTube link."""
    pattern = re.compile(
        r"(https?://)?(www\.)?"
        r"(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)"
        r"[\w\-]{11}"
    )
    return bool(pattern.search(url))


def get_video_info(url: str) -> dict:
    """Fetch lightweight video metadata without downloading."""
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-playlist",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp metadata error: {result.stderr[:300]}")
    return json.loads(result.stdout)


def download_video_segment(url: str, out_path: str, start: int, duration: int) -> None:
    """
    Download a short segment using yt-dlp + ffmpeg section cutting.
    Targets ≤720p to stay lightweight on cloud hardware.
    """
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]",
        "--merge-output-format", "mp4",
        "--download-sections", f"*{start}-{start + duration}",
        "--force-keyframes-at-cuts",
        "-o", out_path,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"Download failed:\n{result.stderr[:500]}")


def generate_script(title: str, description: str, style: str, duration: int) -> str:
    """
    Build a short script from the video's title/description.
    Targets ~150 wpm reading speed scaled to clip duration.
    """
    # Word budget: 150 words/min, leave 10 % margin
    max_words = int(duration * 150 / 60 * 0.90)

    intros = {
        "energetic":  "🔥 You NEED to see this.",
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

    # Grab first ~400 chars of description for context
    desc_snippet = (description or "")[:400].strip()
    body = desc_snippet if desc_snippet else title

    # Combine and trim to word budget
    full = f"{intros[style]} {title}. {body} {outros[style]}"
    words = full.split()
    if len(words) > max_words:
        words = words[:max_words - 4]
        words.append(outros[style])
    return " ".join(words)


async def _tts_async(script: str, voice: str, audio_path: str) -> None:
    """Async Edge-TTS call — wraps the coroutine for asyncio.run()."""
    import edge_tts
    communicate = edge_tts.Communicate(script, voice)
    await communicate.save(audio_path)


def generate_voiceover(script: str, voice: str, audio_path: str) -> None:
    """Generate MP3 voiceover via Edge-TTS (Microsoft Azure neural voices, free)."""
    asyncio.run(_tts_async(script, voice, audio_path))


def get_audio_duration(audio_path: str) -> float:
    """Use ffprobe to get the exact audio duration in seconds."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return float(result.stdout.strip())


def build_caption_filter(script: str, audio_dur: float) -> str:
    """
    Create an ffmpeg drawtext filter that shows word-wrapped captions
    centred at the bottom third of the frame.
    Very lightweight: no ASS/SRT subtitle track needed.
    """
    # Wrap at ~35 chars per line for phone screens
    wrapped = textwrap.fill(script, width=35)
    # Escape single quotes and special chars for ffmpeg filter syntax
    safe = (
        wrapped
        .replace("\\", "\\\\")
        .replace("'", "\u2019")   # curly apostrophe avoids shell quoting issues
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
    """
    Crop + scale to 9:16, mix in voiceover, burn captions.
    Pure FFmpeg — no MoviePy runtime overhead.
    """
    audio_dur = get_audio_duration(audio_path)
    caption_filter = build_caption_filter(script, audio_dur)

    # crop=ih*9/16:ih centres a 9:16 window on the full-height source
    video_filter = (
        f"crop=ih*9/16:ih,"
        f"scale={target_w}:{target_h},"
        f"{caption_filter}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", raw_video,
        "-i", audio_path,
        "-t", str(audio_dur),          # trim to voiceover length
        "-filter_complex", f"[0:v]{video_filter}[vout]",
        "-map", "[vout]",
        "-map", "1:a",                 # use TTS audio, discard original
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


# ══════════════════════════════════════════════════════════════════════════════
# UI — inputs
# ══════════════════════════════════════════════════════════════════════════════

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
    voice = st.selectbox(
        "Voice",
        {
            "Aria (US Female)": "en-US-AriaNeural",
            "Guy (US Male)": "en-US-GuyNeural",
            "Jenny (US Female)": "en-US-JennyNeural",
            "Ryan (UK Male)": "en-GB-RyanNeural",
            "Sonia (UK Female)": "en-GB-SoniaNeural",
        },
        label_visibility="collapsed",
    )
    # Map display name → TTS voice ID
    VOICE_MAP = {
        "Aria (US Female)": "en-US-AriaNeural",
        "Guy (US Male)": "en-US-GuyNeural",
        "Jenny (US Female)": "en-US-JennyNeural",
        "Ryan (UK Male)": "en-GB-RyanNeural",
        "Sonia (UK Female)": "en-GB-SoniaNeural",
    }
    voice_id = VOICE_MAP[voice]

# ── Custom script override ─────────────────────────────────────────────────────
with st.expander("✏️  Override script (optional)"):
    custom_script = st.text_area(
        "Write your own narration script (leave blank to auto-generate from video title/description):",
        height=120,
        placeholder="The world's greatest discovery happened by accident...",
    )

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# Generate button + pipeline
# ══════════════════════════════════════════════════════════════════════════════

if st.button("⚡  Generate Short"):

    # ── Input validation ───────────────────────────────────────────────────────
    if not yt_url.strip():
        st.error("Please paste a YouTube URL above.")
        st.stop()

    if not validate_youtube_url(yt_url.strip()):
        st.error("That doesn't look like a valid YouTube URL. Check the link and try again.")
        st.stop()

    # ── Pipeline ───────────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_video   = os.path.join(tmpdir, "raw.mp4")
        audio_file  = os.path.join(tmpdir, "voice.mp3")
        output_file = os.path.join(tmpdir, "short.mp4")

        progress = st.progress(0)
        status   = st.empty()

        try:
            # Step 1 — metadata
            status.info("🔍 Fetching video info…")
            info = get_video_info(yt_url.strip())
            title       = info.get("title", "Untitled")
            description = info.get("description", "")
            progress.progress(10)

            st.caption(f"**Found:** {title}")

            # Step 2 — script
            status.info("✍️  Generating script…")
            script = custom_script.strip() if custom_script.strip() else generate_script(
                title, description, style, clip_duration
            )
            progress.progress(20)

            with st.expander("📄 Script preview"):
                st.write(script)

            # Step 3 — voiceover
            status.info("🎙️  Generating voiceover with Edge-TTS…")
            generate_voiceover(script, voice_id, audio_file)
            progress.progress(45)

            # Step 4 — download segment
            status.info("⬇️  Downloading video segment (this may take a moment)…")
            download_video_segment(yt_url.strip(), raw_video, int(clip_start), clip_duration)
            progress.progress(70)

            # Step 5 — compose
            status.info("🎞️  Composing vertical short (crop → caption → mix)…")
            compose_short(raw_video, audio_file, script, output_file)
            progress.progress(95)

            # Step 6 — deliver
            status.empty()
            progress.progress(100)

            st.success("✅ Your short is ready!")

            with open(output_file, "rb") as f:
                video_bytes = f.read()

            # Inline preview
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

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("""
<hr style="border-color:#1e1e22; margin-top:2rem;">
<p style="text-align:center; color:#444; font-size:0.8rem;">
  Powered by yt-dlp · Edge-TTS · FFmpeg &nbsp;|&nbsp; Respects YouTube ToS — personal use only.
</p>
""", unsafe_allow_html=True)
