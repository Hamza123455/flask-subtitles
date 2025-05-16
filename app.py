from flask import Flask, render_template, request, send_file
import subprocess, requests, time, os

app = Flask(__name__)
ASSEMBLYAI_API_KEY = "e89c52b5983f4fcfbad631db7f43bd7d"
UPLOAD_ENDPOINT = "https://api.assemblyai.com/v2/upload"
TRANSCRIPT_ENDPOINT = "https://api.assemblyai.com/v2/transcript"

@app.route('/')
def index():
    return render_template('index.html', step="upload")

@app.route('/upload', methods=['POST'])
def upload():
    video = request.files['video']
    video.save('input.mp4')

    # Upload to AssemblyAI
    with open('input.mp4', 'rb') as f:
        res = requests.post(UPLOAD_ENDPOINT,
                            headers={'authorization': ASSEMBLYAI_API_KEY},
                            data=f)
    audio_url = res.json()['upload_url']

    # Request transcription in Urdu
    json = {
        "audio_url": audio_url,
        "language_code": "ur",
        "format_text": True,
        "punctuate": True
    }

    res = requests.post(TRANSCRIPT_ENDPOINT,
                        json=json,
                        headers={'authorization': ASSEMBLYAI_API_KEY})

    transcript_id = res.json()['id']
    polling_endpoint = TRANSCRIPT_ENDPOINT + '/' + transcript_id

    # Poll until complete
    while True:
        res = requests.get(polling_endpoint, headers={'authorization': ASSEMBLYAI_API_KEY})
        data = res.json()
        if data['status'] == 'completed':
            break
        elif data['status'] == 'error':
            return f"Transcription failed: {data['error']}"
        time.sleep(3)

    text = data['text']
    return render_template('index.html', step="edit", subtitles=text)

@app.route('/burn', methods=['POST'])
def burn():
    subtitles = request.form['subtitles']

    # Create SRT file
    with open("subs.srt", "w", encoding='utf-8') as f:
        f.write("1\n00:00:00,000 --> 00:00:10,000\n" + subtitles.strip() + "\n")

    subprocess.run([
        'ffmpeg', '-i', 'input.mp4', '-vf', 'subtitles=subs.srt',
        '-c:a', 'copy', 'static/output.mp4', '-y'
    ])

    return render_template("index.html", step="done")

@app.route('/download')
def download():
    return send_file("static/output.mp4", as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
