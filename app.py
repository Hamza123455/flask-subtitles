from flask import Flask, render_template, request, send_file
import subprocess
import requests
import time
import os

app = Flask(__name__)

ASSEMBLYAI_API_KEY = "e89c52b5983f4fcfbad631db7f43bd7d"
HEADERS = {
    "authorization": ASSEMBLYAI_API_KEY,
    "content-type": "application/json"
}

UPLOAD_ENDPOINT = "https://api.assemblyai.com/v2/upload"
TRANSCRIPT_ENDPOINT = "https://api.assemblyai.com/v2/transcript"


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload():
    video = request.files['video']
    video.save('input.mp4')

    # Upload video to AssemblyAI
    with open('input.mp4', 'rb') as f:
        response = requests.post(UPLOAD_ENDPOINT, headers={"authorization": ASSEMBLYAI_API_KEY}, files={"file": f})
    audio_url = response.json()['upload_url']

    # Send transcription request with Urdu
    json_data = {
        "audio_url": audio_url,
        "language_code": "ur",
        "speech_model": "nano"
    }

    response = requests.post(TRANSCRIPT_ENDPOINT, json=json_data, headers=HEADERS)
    transcript_id = response.json()['id']

    # Wait for transcription to complete
    while True:
        poll_response = requests.get(f"{TRANSCRIPT_ENDPOINT}/{transcript_id}", headers=HEADERS)
        status = poll_response.json()['status']
        if status == 'completed':
            break
        elif status == 'error':
            return f"Transcription failed: {poll_response.json()['error']}"
        time.sleep(3)

    # Get subtitle SRT
    srt_response = requests.get(f"{TRANSCRIPT_ENDPOINT}/{transcript_id}/srt", headers=HEADERS)
    srt_text = srt_response.text

    # Show subtitles in textarea for editing
    return render_template("edit.html", subtitles=srt_text)


@app.route('/burn', methods=['POST'])
def burn():
    # Save edited subtitles to file
    edited_srt = request.form['subtitles']
    with open("subs.srt", "w", encoding="utf-8") as f:
        f.write(edited_srt)

    # Burn subtitles
    subprocess.run([
        'ffmpeg', '-i', 'input.mp4', '-vf', 'subtitles=subs.srt',
        '-c:a', 'copy', 'static/output.mp4', '-y'
    ])

    return "Done! <a href='/download'>Download Subtitled Video</a>"


@app.route('/download')
def download():
    return send_file("static/output.mp4", as_attachment=True)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
