from flask import Flask, render_template, request, send_file
import subprocess
import requests
import time

app = Flask(__name__)

ASSEMBLYAI_API_KEY = 'b9ec1afdcb8f44d98dda19abc0ccebf0'  # <--- Replace with your key
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
    json = {
        "audio_url": upload_url,
        "language_code": "ur",  # Urdu language code
        "auto_chapters": False,
        "auto_highlights": False,
        "format_text": True,
        "punctuate": True,
        "language_model": "assemblyai_default"
    }
    response = requests.post(TRANSCRIPT_ENDPOINT, json=json, headers=headers)
    return response.json()['id']

def wait_for_completion(transcript_id):
    polling_endpoint = f"{TRANSCRIPT_ENDPOINT}/{transcript_id}"
    while True:
        response = requests.get(polling_endpoint, headers=headers).json()
        if response['status'] == 'completed':
            return response
        elif response['status'] == 'error':
            raise Exception("Transcription failed: " + response['error'])
        time.sleep(5)

def save_srt_file(transcript_json):
    srt_text = transcript_json.get('words', [])
    # AssemblyAI does not return srt directly; we will build a simple srt file:
    # For simplicity, we will use `transcript_json['words']` timestamps

    # Or use the 'text' and 'words' timestamps to create srt
    
    words = transcript_json.get('words', [])
    if not words:
        # fallback, just save full transcript in srt format with 1 entry
        with open('subs.srt', 'w', encoding='utf-8') as f:
            f.write(f"1\n00:00:00,000 --> 00:10:00,000\n{transcript_json['text']}\n")
        return
    
    # Split words into subtitle chunks (e.g. 5 seconds chunks)
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

    # Upload video to AssemblyAI
    upload_url = upload_file_to_assemblyai('input.mp4')

    # Request Urdu transcription
    transcript_id = request_transcription(upload_url)

    # Wait for completion
    transcript_json = wait_for_completion(transcript_id)

    # Save subtitles file
    save_srt_file(transcript_json)

    # Burn subtitles into video using ffmpeg
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
