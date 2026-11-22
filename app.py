import gradio as gr
import subprocess
import os
import re
import time
import requests
import imageio_ffmpeg

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "in", "on", "at", "to", "for",
    "of", "with", "and", "or", "but", "over", "under", "every", "this", "that",
    "you", "your", "it", "its", "as", "by", "from", "into", "new", "brings", "build"
}

def extract_keywords(sentence):
    words = re.findall(r"[a-zA-Z]+", sentence.lower())
    keywords = [w for w in words if w not in STOPWORDS and len(w) > 2]
    return ",".join(keywords[:3]) if keywords else "nature,landscape"

def download_scene_image(sentence, img_path, index):
    tags = extract_keywords(sentence)
    urls = [
        f"https://loremflickr.com{tags}?lock={index + 10}",
        f"https://picsum.photos{index + 50}/1280/720"
    ]
    headers = {"User-Agent": "Mozilla/5.0"}

    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
            if resp.status_code == 200 and len(resp.content) > 10000:
                with open(img_path, "wb") as f:
                    f.write(resp.content)
                return True
        except Exception:
            continue

    subprocess.run([
        FFMPEG_EXE, "-y", "-f", "lavfi", "-i", "color=c=0x1e293b:s=1280x720:d=1",
        "-frames:v", "1", img_path
    ], check=True)
    return False

def generate_text_to_video(script_text, voice_choice):
    if not script_text or not script_text.strip():
        raise gr.Error("Please enter your script first!")

    os.makedirs("temp", exist_ok=True)
    audio_path = "temp/voiceover.mp3"
    final_video = "temp/final_text_to_video.mp4"

    # 1. Generate AI Voiceover
    subprocess.run([
        "edge-tts", "--voice", voice_choice,
        "--text", script_text.strip(), "--write-media", audio_path
    ], check=True)

    # 2. Measure exact voiceover length
    probe = subprocess.run(
        [FFMPEG_EXE, "-i", audio_path],
        stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    )
    duration = 10.0
    for line in probe.stderr.splitlines():
        if "Duration:" in line:
            after_dur = line.split("Duration:", 1)[1]
            t = after_dur.split(",", 1)[0].strip()
            h, m, s = t.split(":")
            duration = int(h) * 3600 + int(m) * 60 + float(s)
            break

    # 3. Split script into scenes & fetch matching HD photos
    sentences = [s.strip() for s in script_text.replace("\n", " ").split(".") if len(s.strip()) > 4]
    if not sentences:
        sentences = [script_text.strip()]

    sentences = sentences[:10]
    scene_duration = max(3.0, duration / len(sentences))
    clip_paths = []

    for i, sentence in enumerate(sentences):
        img_path = f"temp/scene_{i:02d}.jpg"
        clip_path = f"temp/clip_{i:02d}.mp4"

        download_scene_image(sentence, img_path, i)

        # Smooth Ken Burns slow zoom effect on each photo
        frames = int(scene_duration * 24)
        subprocess.run([
            FFMPEG_EXE, "-y", "-loop", "1", "-i", img_path,
            "-vf", f"scale=1600:900,zoompan=z='min(zoom+0.0008,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x720",
            "-c:v", "libx264", "-preset", "ultrafast", "-t", f"{scene_duration:.2f}",
            "-pix_fmt", "yuv420p", "-r", "24", clip_path
        ], check=True)
        clip_paths.append(clip_path)
        time.sleep(0.3)

    # 4. Stitch all scenes together
    list_file = "temp/scenes.txt"
    with open(list_file, "w") as f:
        for c in clip_paths:
            f.write(f"file '{os.path.abspath(c)}'\n")

    merged_video = "temp/merged.mp4"
    subprocess.run([
        FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_file,
        "-c:v", "copy", merged_video
    ], check=True)

    # 5. Combine visuals + AI voiceover into final downloadable MP4
    subprocess.run([
        FFMPEG_EXE, "-y", "-i", merged_video, "-i", audio_path,
        "-c:v", "copy", "-c:a", "aac", "-shortest", final_video
    ], check=True)

    return final_video

app = gr.Interface(
    fn=generate_text_to_video,
    inputs=[
        gr.Textbox(
            lines=6,
            placeholder="Type your script here. Each sentence ending with a period (.) becomes a scene!",
            label="1. Enter Your Script (Text-to-Video)"
        ),
        gr.Dropdown(
            choices=["en-US-AndrewNeural", "en-US-AvaNeural", "en-IN-NeerjaNeural", "en-IN-PrabhatNeural"],
            value="en-US-AndrewNeural",
            label="2. Choose AI Voice"
        )
    ],
    outputs=gr.Video(label="3. Download Your Final Video"),
    title="AI Text-to-Video Generator",
    description="Enter your script, click Submit, and download a complete video with real visuals and AI voiceover.",
    flagging_mode="never"
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.launch(server_name="0.0.0.0", server_port=port)
