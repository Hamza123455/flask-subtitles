from flask import Flask, render_template, request, send_file
import subprocess
import requests
import time
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Load API keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")

app = Flask(__name__)

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
        "auto_chapters": False,
        "speaker_labels": False,
        "language_detection": True  # Let AssemblyAI detect language automatically
    }
    response = requests.post(TRANSCRIPT_ENDPOINT, json=json_data, headers=headers)
    data = response.json()
    if 'id' not in data:
        raise Exception(f"Transcription request failed: {data}")
    return data['id']

def wait_for_completion(transcript_id):
    polling_endpoint = f"{TRANSCRIPT_ENDPOINT}/{transcript_id}"
    while True:
        response = requests.get(polling_endpoint, headers=headers).json()
        status = response.get('status')
        if status == 'completed':
            return response
        elif status == 'error':
            raise Exception("Transcription failed: " + response.get('error', 'Unknown error'))
        elif status is None:
            raise Exception(f"Unexpected response: {response}")
        time.sleep(5)

def translate_text_deepl(text):
    url = "https://api-free.deepl.com/v2/translate"
    params = {
        'auth_key': OPENAI_API_KEY,
        'text': text,
        'target_lang': 'UR'  # Urdu
    }
    response = requests.post(url, data=params)
    if response.status_code != 200:
        raise Exception(f"DeepL translation failed: {response.text}")
    return response.json()['translations'][0]['text']

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

    upload_url = upload_file_to_assemblyai('input.mp4')
    transcript_id = request_transcription(upload_url)
    transcript_json = wait_for_completion(transcript_id)

    translated = translate_text_deepl(transcript_json.get('text', ''))
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
    app.run(host='0.0.0.0', port=5000)
