"""
XVidiX — Web tabanlı video indirici
Kurulum: pip install flask yt-dlp
"""

import os, uuid, threading, glob, re
from flask import Flask, render_template, request, jsonify, send_file, after_this_request

app = Flask(__name__)

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

jobs = {}

def new_job():
    jid = str(uuid.uuid4())
    jobs[jid] = {"status": "running", "msg": "Başlatılıyor…", "file": None}
    return jid

def finish_job(jid, filepath):
    jobs[jid] = {"status": "done", "msg": "Tamamlandı ✓", "file": filepath}

def fail_job(jid, msg):
    jobs[jid] = {"status": "error", "msg": msg, "file": None}

def update_msg(jid, msg):
    if jid in jobs:
        jobs[jid]["msg"] = msg

def get_cookie_file():
    """Cookie dosyasını bul veya env variable'dan oluştur."""
    cookies_env = os.environ.get("YOUTUBE_COOKIES")
    if cookies_env:
        path = os.path.join(DOWNLOAD_DIR, "yt_cookies.txt")
        with open(path, "w") as f:
            f.write(cookies_env)
        return path
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
    return local if os.path.exists(local) else None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.json
    url  = (data.get("url") or "").strip()
    fmt  = data.get("fmt", "mp4")

    if not url:
        return jsonify(error="URL boş olamaz"), 400

    jid = new_job()

    def run():
        out_tpl     = os.path.join(DOWNLOAD_DIR, f"{jid}_%(title)s.%(ext)s")
        cookie_file = get_cookie_file()

        opts = {
            "outtmpl"     : out_tpl,
            "quiet"       : True,
            "no_warnings" : True,
            "cookiefile"  : cookie_file,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            },
            "extractor_args": {
                "youtube": {
                    "player_client": ["android"],
                }
            },
        }

        if fmt == "mp3":
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        elif fmt == "mp4":
            opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            opts["merge_output_format"] = "mp4"
        else:
            opts["format"] = "best"

        try:
            update_msg(jid, "İndiriliyor…")
            import yt_dlp
            with yt_dlp.YoutubeDL(opts) as ydl:
                info  = ydl.extract_info(url, download=True)
                fname = ydl.prepare_filename(info)
                if fmt == "mp3":
                    fname = os.path.splitext(fname)[0] + ".mp3"
                if not os.path.exists(fname):
                    matches = glob.glob(os.path.join(DOWNLOAD_DIR, f"{jid}_*"))
                    fname = matches[0] if matches else fname
            finish_job(jid, fname)
        except Exception as e:
            fail_job(jid, str(e))

    threading.Thread(target=run, daemon=True).start()
    return jsonify(job_id=jid)

@app.route("/api/status/<jid>")
def api_status(jid):
    job = jobs.get(jid)
    if not job:
        return jsonify(error="Bulunamadı"), 404
    return jsonify(status=job["status"], msg=job["msg"], ready=job["status"] == "done")

@app.route("/api/file/<jid>")
def api_file(jid):
    job = jobs.get(jid)
    if not job or job["status"] != "done" or not job["file"]:
        return jsonify(error="Hazır değil"), 404

    filepath = job["file"]
    if not os.path.exists(filepath):
        return jsonify(error="Dosya bulunamadı"), 404

    fname = re.sub(r'^[a-f0-9\-]{36}_', '', os.path.basename(filepath))

    @after_this_request
    def cleanup(response):
        try:
            os.remove(filepath)
            del jobs[jid]
        except: pass
        return response

    return send_file(filepath, as_attachment=True, download_name=fname)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀  XVidiX → http://localhost:{port}")
    app.run(debug=False, host="0.0.0.0", port=port)
