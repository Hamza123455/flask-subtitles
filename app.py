from flask import Flask, request, jsonify, send_file
import requests, os, time, subprocess
from werkzeug.utils import secure_filename

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ASSEMBLYAI_API_KEY = os.environ.get('ASSEMBLYAI_API_KEY')

@app.route('/upload', methods=['POST'])
def upload_video():
    video = request.files['video']
    filename = secure_filename(video.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    video.save(filepath)

    transcript_id = upload_and_transcribe(filepath)
    if not transcript_id:
        return jsonify({'error': 'Transcription failed'}), 500

    srt_file = filepath + '.srt'
    if not get_subtitles(transcript_id, srt_file):
        return jsonify({'error': 'Subtitle download failed'}), 500

    output_path = filepath.replace('.mp4', '_subtitled.mp4')
    burn_subtitles(filepath, srt_file, output_path)

    return send_file(output_path, as_attachment=True)

def upload_and_transcribe(filepath):
    headers = {'authorization': ASSEMBLYAI_API_KEY}
    with open(filepath, 'rb') as f:
        upload_res = requests.post('https://api.assemblyai.com/v2/upload', headers=headers, files={'file': f})
    if upload_res.status_code != 200:
        return None
    audio_url = upload_res.json()['upload_url']

    transcribe_res = requests.post(
        'https://api.assemblyai.com/v2/transcript',
        headers=headers,
        json={'audio_url': audio_url, 'subtitles_format': 'srt'}
    )
    return transcribe_res.json().get('id')

def get_subtitles(transcript_id, srt_file):
    headers = {'authorization': ASSEMBLYAI_API_KEY}
    url = f'https://api.assemblyai.com/v2/transcript/{transcript_id}'

    for _ in range(30):  # wait ~2.5 minutes max
        res = requests.get(url, headers=headers)
        status = res.json()
        if status['status'] == 'completed':
            srt_res = requests.get(url + "/subtitles?srt", headers=headers)
            with open(srt_file, 'w') as f:
                f.write(srt_res.text)
            return True
        elif status['status'] == 'error':
            return False
        time.sleep(5)
    return False

def burn_subtitles(input_path, srt_path, output_path):
    subprocess.run([
        'ffmpeg', '-y', '-i', input_path,
        '-vf', f'subtitles={srt_path}',
        '-c:a', 'copy', output_path
    ])
