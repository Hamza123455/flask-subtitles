from flask import Flask, render_template, request, send_file
import subprocess
import requests
import time
import os
from googletrans import Translator
import sys

app = Flask(__name__)

ASSEMBLYAI_API_KEY = 'e89c52b5983f4fcfbad631db7f43bd7d'
UPLOAD_ENDPOINT = 'https://api.assemblyai.com/v2/upload'
TRANSCRIPT_ENDPOINT = 'https://api.assemblyai.com/v2/transcript'

headers = {
    'authorization': ASSEMBLYAI_API_KEY,
    'content-type': 'application/json'
}

def upload_file_to_assemblyai(filename):
    with open(filename, 'rb') as f:
        response = requests.post(UPLOAD_ENDPOINT, headers={'authorization': ASSEMBLYAI_API_KEY}, data=f)
    data = response.json()
    if 'upload_url' not in data:
        raise Exception(f"Upload failed: {data}")
    return data['upload_url']

def request_transcription(upload_url):
    json_data = {
        "audio_url": upload_url,
        "format_text": True,
        "punctuate": True,
        "language_code": "en"
    }
    response = requests.post(TRANSCRIPT_ENDPOINT, json=json_data, headers=headers)
    data = response.json()
    if 'id' not in data:
        raise Exception(f"Transcription request failed: {data}")
    return data['id']

def wait_for_completion(transcript_id):
    polling_endpoint = f"{TRANSCRIPT_ENDPOINT}/{transcript_id}"
    while True:
        response = requests.get(polling_endpoint, headers=headers)
        print(f"[Polling] Status code: {response.status_code}")
        print(f"[Polling] Response text: {response.text}")
        sys.stdout.flush()

        if response.status_code != 200:
            raise Exception(f"Polling failed with status {response.status_code}: {response.text}")

        try:
            data = response.json()
        except Exception as e:
            raise Exception(f"Polling JSON parse error: {e}\nResponse text: {response.text}")

        if data['status'] == 'completed':
            return data
        elif data['status'] == 'error':
            raise Exception("Transcription failed: " + data.get('error', 'Unknown error'))

        time.sleep(5)

def translate_text(text, target_lang='ur'):
    translator = Translator()
    translated = translator.translate(text, dest=target_lang)
    return translated.text

def create_srt(transcript_json, translated_text):
    words = transcript_json.get('words', [])
    if not words:
        with open('subs.srt', 'w', encoding='utf-8') as f:
            f.write(f"1\n00:00:00,000 --> 00:10:00,000\n{translated_text}\n")
        return

    segments = []
    chunk = []
    chunk_start = None
    chunk_end = None
    max_duration_ms = 5000

    for word in words:
        start = word['start']
        end = word['end']
        if chunk_start is None:
            chunk_start = start
        chunk_end = end
        chunk.append((start, end))
        if chunk_end - chunk_start > max_duration_ms:
            segments.append((chunk_start, chunk_end))
            chunk = []
            chunk_start = None
            chunk_end = None

    if chunk:
        segments.append((chunk_start, chunk_end))

    urdu_lines = translated_text.split(' ')
    avg_words = max(1, len(urdu_lines) // len(segments))

    def ms_to_srt_time(ms):
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    with open('subs.srt', 'w', encoding='utf-8') as f:
        i = 0
        for idx, (start, end) in enumerate(segments):
            line = ' '.join(urdu_lines[i:i+avg_words])
            i += avg_words
            f.write(f"{idx+1}\n")
            f.write(f"{ms_to_srt_time(start)} --> {ms_to_srt_time(end)}\n")
            f.write(line + "\n\n")

def read_srt_file():
    if os.path.exists('subs.srt'):
        with open('subs.srt', 'r', encoding='utf-8') as f:
            return f.read()
    return ""

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    video = request.files['video']
    video.save('input.mp4')

    try:
        print("Uploading file to AssemblyAI...")
        sys.stdout.flush()
        upload_url = upload_file_to_assemblyai('input.mp4')
        print(f"Upload URL: {upload_url}")
        sys.stdout.flush()

        print("Requesting transcription...")
        sys.stdout.flush()
        transcript_id = request_transcription(upload_url)
        print(f"Transcript ID: {transcript_id}")
        sys.stdout.flush()

        print("Waiting for transcription to complete...")
        sys.stdout.flush()
        transcript_json = wait_for_completion(transcript_id)
        print("Transcription completed.")
        sys.stdout.flush()
    except Exception as e:
        print(f"Error: {e}")
        sys.stdout.flush()
        return f"Error during transcription process: {e}"

    translated = translate_text(transcript_json.get('text', ''))
    create_srt(transcript_json, translated)

    srt_text = read_srt_file()
    return render_template('edit.html', srt_text=srt_text)

@app.route('/save_subtitles', methods=['POST'])
def save_subtitles():
    edited_srt = request.form['srt']
    with open('subs.srt', 'w', encoding='utf-8') as f:
        f.write(edited_srt)

    subprocess.run([
        'ffmpeg', '-i', 'input.mp4', '-vf', 'subtitles=subs.srt',
        '-c:a', 'copy', 'static/output.mp4', '-y'
    ])

    return "Done! <a href='/download'>Download Subtitled Video</a>"

@app.route('/download')
def download():
    return send_file("static/output.mp4", as_attachment=True)

if __name__ == '__main__':
    if not os.path.exists('static'):
        os.makedirs('static')
    app.run(host='0.0.0.0', port=5000)
