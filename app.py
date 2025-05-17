from flask import Flask, render_template, request, send_file
import subprocess
import requests
import time
import os
import openai

app = Flask(__name__)

# === CONFIGURATION ===
ASSEMBLYAI_API_KEY = 'e89c52b5983f4fcfbad631db7f43bd7d'
OPENAI_API_KEY = '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'  # Use your OpenAI key here
openai.api_key = OPENAI_API_KEY

UPLOAD_ENDPOINT = 'https://api.assemblyai.com/v2/upload'
TRANSCRIPT_ENDPOINT = 'https://api.assemblyai.com/v2/transcript'

HEADERS_ASSEMBLY = {
    'authorization': ASSEMBLYAI_API_KEY,
    'content-type': 'application/json'
}

# === FUNCTIONS ===
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
        "language_detection": True,
        "format_text": True,
        "punctuate": True,
        "auto_chapters": False,
        "iab_categories": False,
        "entity_detection": False,
        "speaker_labels": False,
        "word_boost": [],
        "boost_param": "low",
        "disfluencies": False,
        "sentiment_analysis": False,
        "auto_highlights": False,
        "summarization": False,
        "utterances": False,
        "paragraphs": False,
        "webhook_url": None
    }
    response = requests.post(TRANSCRIPT_ENDPOINT, json=json_data, headers=HEADERS_ASSEMBLY)
    data = response.json()
    if 'id' not in data:
        raise Exception(f"Transcription request failed: {data}")
    return data['id']

def wait_for_completion(transcript_id):
    polling_endpoint = f"{TRANSCRIPT_ENDPOINT}/{transcript_id}"
    while True:
        response = requests.get(polling_endpoint, headers=HEADERS_ASSEMBLY).json()
        if response['status'] == 'completed':
            return response
        elif response['status'] == 'error':
            raise Exception("Transcription failed: " + response.get('error', 'Unknown error'))
        time.sleep(5)

def translate_to_urdu_gpt(text):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a professional translator that translates anything into fluent Urdu."},
                {"role": "user", "content": f"Translate this into Urdu: {text}"}
            ]
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        print("[Translation Error]", e)
        return text

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

# === ROUTES ===
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

    original_text = transcript_json.get('text', '')
    translated = translate_to_urdu_gpt(original_text)
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
