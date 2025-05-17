from flask import Flask, render_template, request, send_file
import subprocess
import requests
import time
import os

app = Flask(__name__)

ASSEMBLYAI_API_KEY = 'e89c52b5983f4fcfbad631db7f43bd7d'
OPENAI_API_KEY = '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'

UPLOAD_ENDPOINT = 'https://api.assemblyai.com/v2/upload'
TRANSCRIPT_ENDPOINT = 'https://api.assemblyai.com/v2/transcript'

headers = {
    'authorization': ASSEMBLYAI_API_KEY,
    'content-type': 'application/json'
}

def upload_file_to_assemblyai(filename):
    with open(filename, 'rb') as f:
        response = requests.post(UPLOAD_ENDPOINT, headers={'authorization': ASSEMBLYAI_API_KEY}, data=f)
    return response.json()['upload_url']

def request_transcription(upload_url):
    json_data = {
        "audio_url": upload_url,
        "punctuate": True,
        "format_text": True,
        "auto_chapters": False,
        "iab_categories": False,
        "language_detection": True,
        "speaker_labels": False,
        "entity_detection": False,
        "sentiment_analysis": False,
        "auto_highlights": False
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
        if response['status'] == 'completed':
            return response
        elif response['status'] == 'error':
            raise Exception("Transcription failed: " + response.get('error', 'Unknown error'))
        time.sleep(5)

def translate_text(text, target_lang='ur'):
    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json'
    }

    prompt = f"Translate the following text to Urdu:\n\n{text}"

    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are a translation assistant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    data = response.json()

    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("[Translation Error]", e)
        print(data)
        return "[Translation failed]"

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
    app.run(host='0.0.0.0', port=5000)
