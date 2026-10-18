import os, re, tempfile, threading
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory, after_this_request
import yt_dlp

ROOT = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=None)
MAX_ACTIVE = int(os.environ.get("MAX_ACTIVE_DOWNLOADS", "1"))
semaphore = threading.BoundedSemaphore(MAX_ACTIVE)
MAX_SIZE_MB = int(os.environ.get("MAX_DOWNLOAD_MB", "500"))
ALLOWED_SCHEMES = ("http://", "https://")

@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")

@app.get("/health")
def health():
    return {"ok": True}

def safe_name(name, ext):
    name = re.sub(r'[^A-Za-z0-9._-]+', '_', name or 'download').strip('._')
    return (name[:100] or 'download') + ext

@app.post("/api/download")
def download():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()
    mode = data.get("mode", "video")
    quality = str(data.get("quality", "best"))
    if not url.startswith(ALLOWED_SCHEMES):
        return jsonify(error="أدخل رابط HTTP أو HTTPS صحيحًا."), 400
    if mode not in ("video", "audio"):
        return jsonify(error="نوع الملف غير مدعوم."), 400
    if quality not in ("best", "1080", "720", "480", "360"):
        return jsonify(error="الجودة المحددة غير صحيحة."), 400
    if not semaphore.acquire(blocking=False):
        return jsonify(error="الخادم مشغول الآن. حاول بعد قليل."), 429

    tempdir = tempfile.mkdtemp(prefix="mrdown_")
    try:
        outtmpl = str(Path(tempdir) / "%(title).80B-%(id)s.%(ext)s")
        if mode == "audio":
            opts = {"format":"bestaudio/best", "outtmpl":outtmpl, "noplaylist":True,
                    "quiet":True, "no_warnings":True, "max_filesize":MAX_SIZE_MB*1024*1024,
                    "postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]}
        else:
            if quality == "best":
                fmt = "bestvideo*+bestaudio/best"
            else:
                fmt = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best[height<={quality}]"
            opts = {"format":fmt, "outtmpl":outtmpl, "noplaylist":True, "quiet":True,
                    "no_warnings":True, "max_filesize":MAX_SIZE_MB*1024*1024,
                    "merge_output_format":"mp4"}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            requested = ydl.prepare_filename(info)
        candidates = [p for p in Path(tempdir).iterdir() if p.is_file() and not p.suffix in (".part",".ytdl")]
        if not candidates:
            raise RuntimeError("لم يتم إنشاء ملف. قد يكون الرابط غير مدعوم أو يحتاج تسجيل دخول.")
        target = max(candidates, key=lambda p:p.stat().st_size)
        if target.stat().st_size > MAX_SIZE_MB*1024*1024:
            raise RuntimeError(f"حجم الملف أكبر من الحد المسموح ({MAX_SIZE_MB} MB).")
        @after_this_request
        def cleanup(response):
            import shutil
            shutil.rmtree(tempdir, ignore_errors=True)
            semaphore.release()
            return response
        return send_file(target, as_attachment=True, download_name=safe_name(info.get("title"), target.suffix or (".mp3" if mode=="audio" else ".mp4")))
    except Exception as exc:
        import shutil
        shutil.rmtree(tempdir, ignore_errors=True)
        semaphore.release()
        message = str(exc)
        if "ffmpeg" in message.lower():
            message = "FFmpeg غير مثبت أو لا يعمل. ثبّته ثم أعد تشغيل الخادم."
        return jsonify(error=message[:500]), 400

if __name__ == "__main__":
    # Local testing only. For internet deployment, use a proper production server and access controls.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8000")), debug=False)
