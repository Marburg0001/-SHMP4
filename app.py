from flask import Flask, request, render_template_string, send_file, jsonify
import yt_dlp
import os
import glob
import uuid
import threading
from werkzeug.utils import secure_filename

app = Flask(__name__)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

download_jobs = {}


def load_html():
    with open("index.html", encoding="utf-8") as f:
        return f.read()


def cleanup_old_downloads():
    for file in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
        try:
            os.remove(file)
        except Exception:
            pass


def detect_platform(url: str) -> str:
    lower = url.lower()
    if "instagram.com" in lower:
        return "Instagram"
    if "tiktok.com" in lower:
        return "TikTok"
    if "facebook.com" in lower or "fb.watch" in lower:
        return "Facebook"
    if "youtube.com" in lower or "youtu.be" in lower:
        return "YouTube"
    return "Bilinmiyor"


@app.route("/", methods=["GET"])
def home():
    html = load_html()
    return render_template_string(html)


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True) or {}
    link = (data.get("link") or "").strip()

    if not link:
        return jsonify({"success": False, "error": "Link boş olamaz."}), 400

    try:
        ydl_opts = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=False)

        title = info.get("title") or "Video hazır"
        thumbnail = info.get("thumbnail") or ""
        platform = detect_platform(link)

        return jsonify({
            "success": True,
            "title": title,
            "thumbnail": thumbnail,
            "platform": platform
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Analiz hatası: {str(e)}"
        }), 500


def download_worker(job_id: str, link: str):
    output_template = os.path.join(DOWNLOAD_DIR, f"{job_id}.%(ext)s")
    download_jobs[job_id] = {
        "status": "starting",
        "percent": 0,
        "filename": None,
        "download_name": None,
        "error": None
    }

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)

            if total and total > 0:
                percent = int(downloaded * 100 / total)
                download_jobs[job_id]["percent"] = max(1, min(percent, 99))
            else:
                current = download_jobs[job_id]["percent"]
                download_jobs[job_id]["percent"] = min(current + 2, 95)

            download_jobs[job_id]["status"] = "downloading"

        elif d["status"] == "finished":
            download_jobs[job_id]["status"] = "processing"
            download_jobs[job_id]["percent"] = 100

    try:
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [progress_hook],
            "merge_output_format": "mp4"
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            filename = ydl.prepare_filename(info)

        if not os.path.exists(filename):
            matches = glob.glob(os.path.join(DOWNLOAD_DIR, f"{job_id}.*"))
            if matches:
                filename = matches[0]

        safe_name = secure_filename(info.get("title", "video"))
        if not safe_name:
            safe_name = "video"

        ext = os.path.splitext(filename)[1] or ".mp4"
        download_name = f"{safe_name}{ext}"

        download_jobs[job_id]["status"] = "done"
        download_jobs[job_id]["percent"] = 100
        download_jobs[job_id]["filename"] = filename
        download_jobs[job_id]["download_name"] = download_name

    except Exception as e:
        download_jobs[job_id]["status"] = "error"
        download_jobs[job_id]["error"] = str(e)


@app.route("/download", methods=["POST"])
def start_download():
    data = request.get_json(silent=True) or {}
    link = (data.get("link") or "").strip()

    if not link:
        return jsonify({"success": False, "error": "Link boş olamaz."}), 400

    job_id = str(uuid.uuid4())
    thread = threading.Thread(target=download_worker, args=(job_id, link), daemon=True)
    thread.start()

    return jsonify({
        "success": True,
        "job_id": job_id
    })


@app.route("/progress/<job_id>", methods=["GET"])
def get_progress(job_id):
    job = download_jobs.get(job_id)

    if not job:
        return jsonify({"success": False, "error": "İş bulunamadı."}), 404

    return jsonify({
        "success": True,
        "status": job["status"],
        "percent": job["percent"],
        "error": job["error"]
    })


@app.route("/file/<job_id>", methods=["GET"])
def get_file(job_id):
    job = download_jobs.get(job_id)

    if not job or job["status"] != "done" or not job["filename"]:
        return "Dosya hazır değil.", 404

    if not os.path.exists(job["filename"]):
        return "Dosya bulunamadı.", 404

    return send_file(
        job["filename"],
        as_attachment=True,
        download_name=job["download_name"] or "video.mp4"
    )


if __name__ == "__main__":
    cleanup_old_downloads()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
