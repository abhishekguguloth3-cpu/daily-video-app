import gradio as gr
import subprocess
import os
import imageio_ffmpeg

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

def create_video(script_text, voice_choice, uploaded_clips):
    if not script_text.strip():
        raise gr.Error("Please enter a voiceover script first.")
    if not uploaded_clips:
        raise gr.Error("Please upload at least one .mp4 video clip.")

    os.makedirs("temp", exist_ok=True)
    audio_path = "temp/voiceover.mp3"
    merged_video = "temp/merged.mp4"
    final_video = "temp/daily_video.mp4"

    # 1. Generate AI Voiceover from text
    subprocess.run([
        "edge-tts", "--voice", voice_choice,
        "--text", script_text, "--write-media", audio_path
    ], check=True)

    # 2. Stitch uploaded clips together
    list_file = "temp/list.txt"
    with open(list_file, "w") as f:
        for clip in uploaded_clips:
            f.write(f"file '{os.path.abspath(clip)}'\n")

    subprocess.run([
        FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_file,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", merged_video
    ], check=True)

    # 3. Combine video + voiceover
    subprocess.run([
        FFMPEG_EXE, "-y", "-i", merged_video, "-i", audio_path,
        "-c:v", "copy", "-c:a", "aac", "-shortest", final_video
    ], check=True)

    return final_video

app = gr.Interface(
    fn=create_video,
    inputs=[
        gr.Textbox(lines=5, placeholder="Write your narration script here...", label="1. Video Script"),
        gr.Dropdown(
            choices=["en-US-AndrewNeural", "en-US-AvaNeural", "en-IN-NeerjaNeural", "en-IN-PrabhatNeural"],
            value="en-US-AndrewNeural",
            label="2. Choose AI Voice"
        ),
        gr.File(file_count="multiple", file_types=[".mp4"], label="3. Upload Video Clips (.mp4)")
    ],
    outputs=gr.Video(label="4. Download Your Final Video"),
    title="Daily AI Voiceover & Video Studio"
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.launch(server_name="0.0.0.0", server_port=port)
