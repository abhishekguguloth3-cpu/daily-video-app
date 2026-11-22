import gradio as gr
import subprocess
import os
import urllib.parse
import requests
import imageio_ffmpeg

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

def generate_text_to_video(script_text, voice_choice):
    if not script_text.strip():
        raise gr.Error("Please enter your script first!")

    os.makedirs("temp", exist_ok=True)
    audio_path = "temp/voiceover.mp3"
    final_video = "temp/final_text_to_video.mp4"

    # 1. Generate AI Voiceover from your text
    subprocess.run([
        "edge-tts", "--voice", voice_choice,
        "--text", script_text, "--write-media", audio_path
    ], check=True)

    # Get audio duration using ffmpeg
    probe = subprocess.run(
        [FFMPEG_EXE, "-i", audio_path],
        stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    )
    duration = 15.0
    for line in probe.stderr.splitlines():
        if "Duration:" in line:
            t = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = t.split(":")
            duration = int(h) * 3600 + int(m) * 60 + float(s)
            break

    # 2. Split script into scenes & generate realistic AI visuals automatically
    sentences = [s.strip() for s in script_text.replace("\n", " ").split(".") if len(s.strip()) > 5]
    if not sentences:
        sentences = [script_text.strip()]

    scene_duration = max(3.0, duration / len(sentences))
    clip_paths = []

    for i, sentence in enumerate(sentences):
        img_path = f"temp/scene_{i:02d}.jpg"
        clip_path = f"temp/clip_{i:02d}.mp4"

        # Generate realistic visual from each sentence
        prompt = urllib.parse.quote(f"cinematic realistic photography, {sentence}, 4k, natural lighting")
        img_url = f"https://pollinations.ai{prompt}?width=1280&height=720&nologo=true&seed={i+42}"
        
        resp = requests.get(img_url, timeout=30)
        with open(img_path, "wb") as f:
            f.write(resp.content)

        # Turn image into smooth cinematic zooming video clip
        frames = int(scene_duration * 25)
        subprocess.run([
            FFMPEG_EXE, "-y", "-loop", "1", "-i", img_path,
            "-vf", f"scale=1920:1080,zoompan=z='min(zoom+0.001,1.15)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x720",
            "-c:v", "libx264", "-t", str(scene_duration), "-pix_fmt", "yuv420p", "-r", "25",
            clip_path
        ], check=True)
        clip_paths.append(clip_path)

    # 3. Join all generated scenes together
    list_file = "temp/scenes.txt"
    with open(list_file, "w") as f:
        for c in clip_paths:
            f.write(f"file '{os.path.abspath(c)}'\n")

    merged_video = "temp/merged.mp4"
    subprocess.run([
        FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_file,
        "-c:v", "copy", merged_video
    ], check=True)

    # 4. Combine visuals + AI voiceover into final MP4
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
            placeholder="Type your story or script here. Each sentence automatically becomes a realistic video scene!",
            label="1. Enter Your Script (Text-to-Video)"
        ),
        gr.Dropdown(
            choices=["en-US-AndrewNeural", "en-US-AvaNeural", "en-IN-NeerjaNeural", "en-IN-PrabhatNeural"],
            value="en-US-AndrewNeural",
            label="2. Choose AI Voice"
        )
    ],
    outputs=gr.Video(label="3. Your Generated Video (Click Top-Right Icon to Download)"),
    title="AI Text-to-Video Generator",
    description="Type your text, click Submit, and get a complete realistic video with voiceover—no uploads needed."
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.launch(server_name="0.0.0.0", server_port=port)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.launch(server_name="0.0.0.0", server_port=port)
