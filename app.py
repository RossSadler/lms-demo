import os
import uuid
import traceback
import threading
from pathlib import Path
from datetime import datetime, timezone

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    send_from_directory,
    send_file,
    abort,
)
from werkzeug.utils import secure_filename

from pipeline.main import run_job, extract_paragraphs, split_into_sections
from pipeline.status import (
    create_job,
    ensure_job_dir,
    get_job_status,
    list_recent_jobs,
    update_job,
    mark_job_started,
    mark_job_completed,
    mark_job_failed,
    job_exists,
)

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = Path(os.getenv("RUNS_DIR", BASE_DIR / "runs")).resolve()
DEMO_SAFE_MODE = os.getenv("DEMO_SAFE_MODE", "true").lower() in {"1", "true", "yes", "on"}
HEYGEN_ENABLED = os.getenv("HEYGEN_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


RUNS_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static"
)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024

ACTIVE_THREADS = {}
ACTIVE_THREADS_LOCK = threading.Lock()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() == ".docx"


def form_checkbox(name: str, default: bool = False) -> bool:
    value = request.form.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "on", "yes"}


def form_int(name: str, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    raw = request.form.get(name, "").strip()
    try:
        value = int(raw)
    except Exception:
        value = default

    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)

    return value


def run_job_background(job_id: str, input_path: str, options: dict) -> None:
    try:
        mark_job_started(job_id)

        job_dir = ensure_job_dir(job_id)

        result = run_job(
            job_id=job_id,
            job_dir=str(job_dir),
            input_path=input_path,
            options=options,
        )

        demo_path = None
        video = None

        if isinstance(result, dict):
            demo_path = result.get("demo_path")
            video = result.get("video")

        mark_job_completed(job_id, demo_path=demo_path)

        if video:
            update_job(job_id, video=video)

    except Exception as exc:
        traceback_text = traceback.format_exc()
        mark_job_failed(job_id, error=str(exc), traceback_text=traceback_text)
    finally:
        with ACTIVE_THREADS_LOCK:
            ACTIVE_THREADS.pop(job_id, None)


@app.route("/", methods=["GET"])
def index():
    jobs = list_recent_jobs(limit=10)
    return render_template("index.html", jobs=jobs, heygen_enabled=HEYGEN_ENABLED, demo_safe_mode=DEMO_SAFE_MODE)


@app.route("/upload", methods=["POST"])
def upload():
    uploaded_file = request.files.get("file")

    if not uploaded_file or uploaded_file.filename == "":
        return render_template(
            "index.html",
            jobs=list_recent_jobs(limit=10),
            heygen_enabled=HEYGEN_ENABLED,
            demo_safe_mode=DEMO_SAFE_MODE,
            error="Please choose a .docx file first.",
        ), 400

    if not allowed_file(uploaded_file.filename):
        return render_template(
            "index.html",
            jobs=list_recent_jobs(limit=10),
            heygen_enabled=HEYGEN_ENABLED,
            demo_safe_mode=DEMO_SAFE_MODE,
            error="Only .docx uploads are supported.",
        ), 400

    run_audio = form_checkbox("run_audio", default=False)
    run_images = form_checkbox("run_images", default=False)
    run_video = form_checkbox("run_video", default=False)
    if not HEYGEN_ENABLED:
        run_video = False
    fast_mode = form_checkbox("fast_mode", default=True)
    smart_defaults = form_checkbox("smart_defaults", default=False)
    no_limit = form_checkbox("no_limit", default=False)

    batch_size = form_int("batch_size", default=5, min_value=1, max_value=50)
    max_total_lessons = form_int("max_total_lessons", default=5, min_value=1, max_value=200)

    job_id = uuid.uuid4().hex[:12]
    safe_name = secure_filename(uploaded_file.filename)

    job_dir = ensure_job_dir(job_id)
    input_dir = job_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    input_path = input_dir / safe_name
    uploaded_file.save(input_path)

    detected_sections = None

    if smart_defaults or no_limit:
        try:
            paragraphs = extract_paragraphs(input_path)
            sections = split_into_sections(paragraphs)
            detected_sections = len(sections)
        except Exception:
            detected_sections = None

    if no_limit and detected_sections:
        max_total_lessons = detected_sections

    elif smart_defaults and detected_sections:
        if detected_sections <= 5:
            batch_size = detected_sections
            max_total_lessons = detected_sections
        elif detected_sections <= 12:
            batch_size = 5
            max_total_lessons = min(detected_sections, 10)
        elif detected_sections <= 25:
            batch_size = 5
            max_total_lessons = 15
        else:
            batch_size = 5
            max_total_lessons = 20

        if fast_mode:
            batch_size = min(batch_size, 3)
            max_total_lessons = min(max_total_lessons, 5)

    create_job(
        job_id=job_id,
        original_filename=safe_name,
        input_path=str(input_path),
    )

    status = update_job(
        job_id,
        run_audio=run_audio,
        run_images=run_images,
        run_video=run_video,
        fast_mode=fast_mode,
        smart_defaults=smart_defaults,
        no_limit=no_limit,
        detected_sections=detected_sections,
        batch_size=batch_size,
        max_total_lessons=max_total_lessons,
        requested_lessons=max_total_lessons,
        message="Document uploaded. Starting your course build.",
    )

    options = {
        "run_lessons": True,
        "run_audio": status.get("run_audio") is True,
        "run_images": status.get("run_images") is True,
        "run_video": status.get("run_video") is True and HEYGEN_ENABLED,
        "fast_mode": status.get("fast_mode") is True,
        "batch_size": int(status.get("batch_size", 5) or 5),
        "max_total_lessons": int(status.get("max_total_lessons", 5) or 5),
        "requested_lessons": int(status.get("requested_lessons", status.get("max_total_lessons", 5)) or 5),
        "demo_safe_mode": DEMO_SAFE_MODE,
    }

    with ACTIVE_THREADS_LOCK:
        existing = ACTIVE_THREADS.get(job_id)

        if not existing or not existing.is_alive():
            thread = threading.Thread(
                target=run_job_background,
                args=(job_id, str(input_path), options),
                daemon=True,
            )
            ACTIVE_THREADS[job_id] = thread
            thread.start()

    return redirect(url_for("progress_page", job_id=job_id))


@app.route("/start/<job_id>", methods=["POST"])
def start_job(job_id):
    if not job_exists(job_id):
        return jsonify({"ok": False, "error": "Course build not found"}), 404

    status = get_job_status(job_id)
    current_state = status.get("state")

    if current_state in {"running", "complete"}:
        return jsonify(
            {
                "ok": True,
                "job_id": job_id,
                "state": current_state,
                "message": f"Course build already {current_state}.",
            }
        )

    input_path = status.get("input_path")
    if not input_path or not Path(input_path).exists():
        update_job(
            job_id,
            state="failed",
            status="failed",
            error="Input file missing.",
            finished_at=utc_now_iso(),
        )
        return jsonify({"ok": False, "error": "Input file missing"}), 400

    options = {
        "run_lessons": True,
        "run_audio": status.get("run_audio") is True,
        "run_images": status.get("run_images") is True,
        "run_video": status.get("run_video") is True and HEYGEN_ENABLED,
        "fast_mode": status.get("fast_mode") is True,
        "batch_size": int(status.get("batch_size", 5) or 5),
        "max_total_lessons": int(status.get("max_total_lessons", 5) or 5),
        "requested_lessons": int(status.get("requested_lessons", status.get("max_total_lessons", 5)) or 5),
        "demo_safe_mode": DEMO_SAFE_MODE,
    }

    with ACTIVE_THREADS_LOCK:
        existing = ACTIVE_THREADS.get(job_id)
        if existing and existing.is_alive():
            return jsonify(
                {
                    "ok": True,
                    "job_id": job_id,
                    "state": "running",
                    "message": "Course build already running.",
                }
            )

        thread = threading.Thread(
            target=run_job_background,
            args=(job_id, input_path, options),
            daemon=True,
        )
        ACTIVE_THREADS[job_id] = thread
        thread.start()

    return jsonify(
        {
            "ok": True,
            "job_id": job_id,
            "state": "queued",
            "message": "Course build started.",
        }
    )


@app.route("/progress/<job_id>", methods=["GET"])
def progress_page(job_id):
    if not job_exists(job_id):
        abort(404)

    return render_template("progress.html", job_id=job_id)


@app.route("/status/<job_id>", methods=["GET"])
def job_status(job_id):
    if not job_exists(job_id):
        return jsonify({"ok": False, "error": "Course build not found"}), 404

    status = get_job_status(job_id)
    return jsonify(status)


@app.route("/result/<job_id>", methods=["GET"])
def result_page(job_id):
    if not job_exists(job_id):
        abort(404)

    status = get_job_status(job_id)
    return render_template("result.html", job=status)


@app.route("/jobs", methods=["GET"])
def jobs_page():
    jobs = list_recent_jobs(limit=100)
    return render_template("jobs.html", jobs=jobs)


@app.route("/demo/<job_id>/", methods=["GET"])
def demo_index(job_id):
    if not job_exists(job_id):
        abort(404)

    job = get_job_status(job_id)
    demo_path = job.get("demo_path")

    if not demo_path:
        abort(404)

    demo_dir = Path(demo_path)
    if not demo_dir.exists():
        abort(404)

    return send_from_directory(demo_dir, "index.html")


@app.route("/demo/<job_id>/<path:filename>", methods=["GET"])
def demo_asset(job_id, filename):
    if not job_exists(job_id):
        abort(404)

    job = get_job_status(job_id)
    demo_path = job.get("demo_path")

    if not demo_path:
        abort(404)

    demo_dir = Path(demo_path)
    if not demo_dir.exists():
        abort(404)

    return send_from_directory(demo_dir, filename)


@app.route("/video/<path:filepath>", methods=["GET"])
def serve_video(filepath):
    full_path = Path(filepath)

    if not full_path.exists() or not full_path.is_file():
        abort(404)

    return send_file(full_path)


@app.route("/delete/<job_id>", methods=["POST"])
def delete_job(job_id):
    if not job_exists(job_id):
        return jsonify({"ok": False, "error": "Course build not found"}), 404

    job_dir = ensure_job_dir(job_id)

    try:
        import shutil
        shutil.rmtree(job_dir)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.errorhandler(404)
def not_found(_err):
    return render_template("result.html", job={"state": "missing", "job_id": None}), 404


@app.errorhandler(413)
def file_too_large(_err):
    return render_template(
        "index.html",
        jobs=list_recent_jobs(limit=10),
        heygen_enabled=HEYGEN_ENABLED,
        demo_safe_mode=DEMO_SAFE_MODE,
        error="Upload too large for current server limit.",
    ), 413


if __name__ == "__main__":
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    port = int(os.getenv("PORT", "5000"))
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.run(host="0.0.0.0", port=port, debug=True)