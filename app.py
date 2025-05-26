from flask import Flask, render_template, request, send_file, jsonify
import subprocess
import requests
import time
import os

# AssemblyAI API Key
ASSEMBLYAI_API_KEY = "e89c52b5983f4fcfbad631db7f43bd7d"

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
        "language_code": "ur",
        "format_text": True,
        "punctuate": True,
        "speech_model": "nano",
        "auto_chapters": False
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
        time.sleep(5)

def create_srt(transcript_json):
    words = transcript_json.get('words', [])
    if not words:
        with open('subs.srt', 'w', encoding='utf-8') as f:
            f.write(f"1\n00:00:00,000 --> 00:10:00,000\n{transcript_json.get('text', '')}\n")
        return

    segments = []
    chunk = []
    chunk_start = None
    chunk_end = None
    max_duration_ms = 5000

    for word in words:
        start = word['start']
        end = word['end']
        text = word['text']

        if chunk_start is None:
            chunk_start = start
        chunk_end = end
        chunk.append(text)

        if chunk_end - chunk_start > max_duration_ms:
            segments.append((chunk_start, chunk_end, ' '.join(chunk)))
            chunk = []
            chunk_start = None
            chunk_end = None

    if chunk:
        segments.append((chunk_start, chunk_end, ' '.join(chunk)))

    def ms_to_srt_time(ms):
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    with open('subs.srt', 'w', encoding='utf-8') as f:
        for i, (start, end, text) in enumerate(segments, 1):
            f.write(f"{i}\n")
            f.write(f"{ms_to_srt_time(start)} --> {ms_to_srt_time(end)}\n")
            f.write(text + "\n\n")

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
        upload_url = upload_file_to_assemblyai('input.mp4')
        transcript_id = request_transcription(upload_url)
        transcript_json = wait_for_completion(transcript_id)

        create_srt(transcript_json)
        srt_text = read_srt_file()
        return render_template('edit.html', srt_text=srt_text)
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/save_subtitles', methods=['POST'])
def save_subtitles():
    edited_srt = request.form['srt']
    with open('subs.srt', 'w', encoding='utf-8') as f:
        f.write(edited_srt)

    return jsonify({"status": "success"})

@app.route('/download_srt')
def download_srt():
    return send_file("subs.srt", as_attachment=True, download_name="subtitles.srt")

@app.route('/download')
def download():
    return "Subtitle burning (MP4) not available on Railway. Please use the .srt file in CapCut or VLC."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
