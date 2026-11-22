import gradio as gr
import subprocess
import os
import time
import urllib.parse
import requests
import imageio_ffmpeg

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

def create_fallback_image(img_path):
    subprocess.run([
        FFMPEG_EXE, "-y", "-f", "lavfi", "-i", "color=c=0x1e293b:s=1280x720:d=1",
        "-frames:v", "1", img_path
    ], check=True)

def generate_text_to_video(script_text, voice_choice):
    if not script_text or not script_text.strip():
        raise gr.Error("Please enter your script first!")

    os.makedirs("temp", exist_ok=True)
    audio_path = "temp/voiceover.mp3"
    final_video = "temp/final_text_to_video.mp4"

    # 1. Generate AI Voiceover
    try:
        subprocess.run([
            "edge-tts", "--voice", voice_choice,
            "--text", script_text.strip(), "--write-media", audio_path
        ], check=True)
    except Exception as e:
        raise gr.Error(f"Voiceover error: {str(e)}")

    # 2. Measure exact voiceover length
    probe = subprocess.run(
        [FFMPEG_EXE, "-i", audio_path],
        stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    )
    duration = 15.0
    for line in probe.stderr.splitlines():
        if "Duration:" in line:
            after_dur = line.split("Duration:", 1)[1]
            t = after_dur.split(",", 1)[0].strip()
            h, m, s = t.split(":")
            duration = int(h) * 3600 + int(m) * 60 + float(s)
            break

    # 3. Split script into scenes & generate visuals safely
    sentences = [s.strip() for s in script_text.replace("\n", " ").split(".") if len(s.strip()) > 5]
    if not sentences:
        sentences = [script_text.strip()]

    # Cap at 10 scenes so Render free CPU never runs out of memory or times out
    sentences = sentences[:10]
    scene_duration = max(3.0, duration / len(sentences))
    clip_paths = []

    for i, sentence in enumerate(sentences):
        img_path = f"temp/scene_{i:02d}.jpg"
        clip_path = f"temp/clip_{i:02d}.mp4"

        prompt = urllib.parse.quote(f"cinematic realistic photography, {sentence}, 4k, natural lighting")
        img_url = f"https://pollinations.ai{prompt}?width=1280&height=720&nologo=true&seed={i+101}"

        got_valid_image = False
        try:
            resp = requests.get(img_url, timeout=30)
            content_type = resp.headers.get("Content-Type", "")
            if resp.status_code == 200 and "image" in content_type and len(resp.content) > 5000:
                with open(img_path, "wb") as f:
                    f.write(resp.content)
                got_valid_image = True
        except Exception:
            pass

        if not got_valid_image:
            create_fallback_image(img_path)

        # Fast scale + subtle zoom that uses low RAM on Render Free tier
        subprocess.run([
            FFMPEG_EXE, "-y", "-loop", "1", "-i", img_path,
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "ultrafast", "-t", f"{scene_duration:.2f}",
            "-pix_fmt", "yuv420p", "-r", "24", clip_path
        ], check=True)
        clip_paths.append(clip_path)
        time.sleep(0.5)

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
    description="Enter your script, click Submit, and download a complete realistic video with voiceover.",
    flagging_mode="never"
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.launch(server_name="0.0.0.0", server_port=port)
