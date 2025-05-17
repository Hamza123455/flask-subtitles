import os
import time
import requests
import subprocess
from flask import Flask, render_template, request, send_file
from dotenv import load_dotenv

load_dotenv()  # Load API keys from .env

app = Flask(__name__)

# Load your API keys from environment
ASSEMBLYAI_API_KEY = os.getenv('ASSEMBLYAI_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

UPLOAD_ENDPOINT = 'https://api.assemblyai.com/v2/upload'
TRANSCRIPT_ENDPOINT = 'https://api.assemblyai.com/v2/transcript'

headers = {
    'authorization': ASSEMBLYAI_API_KEY,
    'content-type': 'application/json'
}

def upload_file_to_assemblyai(filename):
    with open(filename, 'rb') as f:
        response = requests.post(UPLOAD_ENDPOINT, headers={'authorization': ASSEMBLYAI_API_KEY}, data=f)
    return response.json().get('upload_url')

def request_transcription(upload_url):
    json_data = {
        "audio_url": upload_url,
        "auto_detect": True,
        "punctuate": True,
        "format_text": True,
        "language_detection": True,
        "speaker_labels": False
    }
    response = requests.post(TRANSCRIPT_ENDPOINT, headers=headers, json=json_data)
    return response.json().get('id')

def wait_for_completion(transcript_id):
    polling_url = f"{TRANSCRIPT_ENDPOINT}/{transcript_id}"
    while True:
        response = requests.get(polling_url, headers=headers).json()
        if response['status'] == 'completed':
            return response
        elif response['status'] == 'error':
            raise Exception(f"Transcription failed: {response.get('error')}")
        time.sleep(5)

def gpt_translate(text, target_lang="Urdu"):
    prompt = f"Translate this text into {target_lang}:\n\n{text}"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    json_data = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": prompt}]
    }
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=json_data)
    return response.json()['choices'][0]['message']['content'].strip()

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

    urdu_words = translated_text.split()
    avg_words = max(1, len(urdu_words) // len(segments))

    def ms_to_srt_time(ms):
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    with open('subs.srt', 'w', encoding='utf-8') as f:
        i = 0
        for idx, (start, end) in enumerate(segments):
            line = ' '.join(urdu_words[i:i+avg_words])
            i += avg_words
            f.write(f"{idx+1}\n")
            f.write(f"{ms_to_srt_time(start)} --> {ms_to_srt_time(end)}\n")
            f.write(line + "\n\n")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    video = request.files['video']
    video.save('input.mp4')

    upload_url = upload_file_to_assemblyai('input.mp4')
    transcript_id = request_transcription(upload_url)
    transcript_data = wait_for_completion(transcript_id)

    original_text = transcript_data.get('text', '')
    translated_text = gpt_translate(original_text)

    create_srt(transcript_data, translated_text)

    with open('subs.srt', 'r', encoding='utf-8') as f:
        srt_text = f.read()

    return render_template('edit.html', srt_text=srt_text)

@app.route('/save_subtitles', methods=['POST'])
def save_subtitles():
    srt_content = request.form['srt']
    with open('subs.srt', 'w', encoding='utf-8') as f:
        f.write(srt_content)

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
