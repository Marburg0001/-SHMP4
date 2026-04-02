from flask import Flask, request, render_template_string, send_file
import yt_dlp
import os
import glob
from werkzeug.utils import secure_filename

app = Flask(__name__)

def load_html():
    with open("index.html", encoding="utf-8") as f:
        return f.read()

def cleanup_old_downloads():
    for file in glob.glob("downloaded_video.*"):
        try:
            os.remove(file)
        except:
            pass

@app.route("/", methods=["GET", "POST"])
def home():
    html = load_html()

    if request.method == "POST":
        link = request.form.get("link", "").strip()

        if not link:
            return html.replace(
                "</body>",
                "<p style='text-align:center;color:red;margin-top:20px;'>Link boş olamaz.</p></body>"
            )

        try:
            cleanup_old_downloads()

            ydl_opts = {
                "format": "best[ext=mp4]/best",
                "outtmpl": "downloaded_video.%(ext)s",
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, download=True)
                filename = ydl.prepare_filename(info)

            safe_name = secure_filename(info.get("title", "video"))
            if not safe_name:
                safe_name = "video"

            ext = os.path.splitext(filename)[1]
            download_name = f"{safe_name}{ext}"

            return send_file(filename, as_attachment=True, download_name=download_name)

        except Exception as e:
            error_html = f"""
            <p style='text-align:center;color:red;margin-top:20px;'>
                Hata oluştu: {str(e)}
            </p>
            </body>
            """
            return html.replace("</body>", error_html)

    return render_template_string(html)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
