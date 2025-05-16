from flask import Flask, render_template, request, send_file
import subprocess
import requests
import time

app = Flask(__name__)

# === Your AssemblyAI API Key ===
ASSEMBLYAI_API_KEY = 'e89c52b5983f4fcfbad631db7f43bd7d'

# === AssemblyAI API Endpoints ===
UPLOAD_ENDPOINT = 'https://api.assemblyai.com/v2/upload'
TRANSCRIPT_ENDPOINT = 'https://api.assemblyai.com/v2/transcript'

# === HTTP Headers ===
headers = {
    'authorization': ASSEMBLYAI_API_KEY,
    'content-type': 'application/json'
}

# === Upload video to AssemblyAI ===
def upload_file_to_assemblyai(filename):
    with open(filename, 'rb') as f:
        response = requests.post(UPLOAD_ENDPOINT, headers={'authorization': ASSEMBLYAI_API_KEY}, data=f)
    data = response.json()
    print("Upload response:", data)  # Debug
    if 'upload_url' not in data:
        raise Exception(f"Upload failed: {data}")
    return data['upload_url']

# === Request transcription in Urdu using nano model ===
def request_transcription(upload_url):
    json = {
        "audio_url": upload_url,
        "language_code": "ur",
        "speech_model": "nano",
        "format_text": True,
        "punctuate": True,
        "words": True
    }
    response = requests.post(TRANSCRIPT_ENDPOINT, json=json, headers=headers)
    data = response.json()
    print("Transcription request response:", data)  # Debug
    if 'id' not in data:
        raise Exception(f"Transcription request failed: {data}")
    return data['id']

# === Wait until transcription completes ===
def wait_for_completion(transcript_id):
    polling_endpoint = f"{TRANSCRIPT_ENDPOINT}/{transcript_id}"
    while True:
        response = requests.get(polling_endpoint, headers=headers).json()
        print("Polling response:", response)  # Debug
        if response['status'] == 'completed':
            return response
        elif response['status'] == 'error':
            raise Exception("Transcription failed: " + response.get('error', 'Unknown error'))
        time.sleep(5)

# === Convert words to SRT subtitle format ===
def save_srt_file(transcript_json):
    words = transcript_json.get('words', [])
    if not words:
        with open('subs.srt', 'w', encoding='utf-8') as f:
            f.write(f"1\n00:00:00,000 --> 00:10:00,000\n{transcript_json.get('text', '')}\n")
        return

    subs = []
    chunk = []
    chunk_start = None
    chunk_end = None
    max_duration_ms = 5000  # 5 seconds

    for word in words:
        start = word['start']
        end = word['end']
        text = word['text']

        if chunk_start is None:
            chunk_start = start
        chunk_end = end
        chunk.append(text)

        if (chunk_end - chunk_start) > max_duration_ms:
            subs.append((chunk_start, chunk_end, ' '.join(chunk)))
            chunk = []
            chunk_start = None
            chunk_end = None

    if chunk:
        subs.append((chunk_start, chunk_end, ' '.join(chunk)))

    def ms_to_srt_time(ms):
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    with open('subs.srt', 'w', encoding='utf-8') as f:
        for i, (start, end, text) in enumerate(subs, 1):
            f.write(f"{i}\n")
            f.write(f"{ms_to_srt_time(start)} --> {ms_to_srt_time(end)}\n")
            f.write(text + "\n\n")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    video = request.files['video']
    video.save('input.mp4')

    # Upload to AssemblyAI
    upload_url = upload_file_to_assemblyai('input.mp4')

    # Request Urdu transcription
    transcript_id = request_transcription(upload_url)

    # Wait for processing
    transcript_json = wait_for_completion(transcript_id)

    # Save original subtitles
    save_srt_file(transcript_json)

    # Load subtitles to show in form
    with open('subs.srt', 'r', encoding='utf-8') as f:
        srt_text = f.read()

    return render_template('edit.html', srt_text=srt_text)

@app.route('/save_subtitles', methods=['POST'])
def save_subtitles():
    srt_text = request.form['srt']
    with open('subs.srt', 'w', encoding='utf-8') as f:
        f.write(srt_text)

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
