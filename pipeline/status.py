import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


BASE_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = Path(os.getenv("RUNS_DIR", BASE_DIR / "runs")).resolve()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_runs_dir() -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return RUNS_DIR


def ensure_job_dir(job_id: str) -> Path:
    job_dir = ensure_runs_dir() / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def job_path(job_id: str) -> Path:
    return ensure_runs_dir() / job_id


def status_path(job_id: str) -> Path:
    return job_path(job_id) / "status.json"


def status_path_from_job_dir(job_dir: Path) -> Path:
    return Path(job_dir) / "status.json"


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(path)


def read_json_file(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def job_exists(job_id: str) -> bool:
    return status_path(job_id).exists()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def compute_progress(data: Dict[str, Any]) -> int:
    state = data.get("state") or data.get("status") or ""
    stage = data.get("stage") or data.get("step") or ""

    if state == "complete":
        return 100

    if state == "failed":
        return min(max(safe_int(data.get("progress"), 0), 0), 100)

    completed_lessons = safe_int(data.get("completed_lessons"), 0)
    total_lessons = max(safe_int(data.get("total_lessons"), 0), 0)

    if stage == "uploaded":
        return 0
    if stage == "starting":
        return 2
    if stage == "parsing":
        return 5
    if stage == "parsed":
        return 10
    if stage == "building_demo":
        return 96
    if stage == "demo_ready":
        return 99
    if stage == "pipeline_complete":
        return 95
    if stage == "complete":
        return 100

    if stage == "lessons":
        if total_lessons > 0:
            ratio = min(max(completed_lessons / total_lessons, 0), 1)
            return int(15 + (40 * ratio))
        return 15

    if stage == "audio":
        if total_lessons > 0:
            ratio = min(max(completed_lessons / total_lessons, 0), 1)
            return int(55 + (25 * ratio))
        return 55

    if stage == "images":
        if total_lessons > 0:
            ratio = min(max(completed_lessons / total_lessons, 0), 1)
            return int(80 + (15 * ratio))
        return 80

    explicit_progress = data.get("progress")
    if explicit_progress is not None:
        return min(max(safe_int(explicit_progress, 0), 0), 100)

    return 0


def default_status_payload(
    job_id: str,
    original_filename: Optional[str] = None,
    input_path: Optional[str] = None,
) -> Dict[str, Any]:
    now = utc_now_iso()
    return {
        "job_id": job_id,
        "state": "uploaded",
        "status": "uploaded",
        "stage": "uploaded",
        "step": "uploaded",
        "message": "File uploaded. Waiting to start.",
        "progress": 0,
        "original_filename": original_filename,
        "input_path": input_path,
        "demo_path": None,
        "error": None,
        "traceback": None,
        "last_error": None,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
        "current_lesson": 0,
        "completed_lessons": 0,
        "total_lessons": 0,
        "run_audio": None,
        "run_images": None,
        "fast_mode": None,
        "max_total_lessons": None,
        "lesson_failures": 0,
        "image_failures": 0,
        "batch_size": None,
        "smart_defaults": None,
        "no_limit": None,
        "detected_sections": None,
    }


def normalise_status_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(data)

    if not data.get("state") and data.get("status"):
        data["state"] = data["status"]

    if not data.get("status") and data.get("state"):
        data["status"] = data["state"]

    if not data.get("step") and data.get("stage"):
        data["step"] = data["stage"]

    if not data.get("stage") and data.get("step"):
        data["stage"] = data["step"]

    data["progress"] = compute_progress(data)
    return data


def create_job(job_id: str, original_filename: str, input_path: str) -> Dict[str, Any]:
    payload = default_status_payload(
        job_id=job_id,
        original_filename=original_filename,
        input_path=input_path,
    )
    atomic_write_json(status_path(job_id), payload)
    return payload


def get_job_status(job_id: str) -> Dict[str, Any]:
    path = status_path(job_id)

    if not path.exists():
        return {
            "job_id": job_id,
            "state": "missing",
            "status": "missing",
            "message": "Job not found.",
            "progress": 0,
            "stage": "missing",
            "step": "missing",
            "error": "Job not found.",
        }

    try:
        data = read_json_file(path)
        return normalise_status_payload(data)
    except Exception as exc:
        return {
            "job_id": job_id,
            "state": "failed",
            "status": "failed",
            "message": "Could not read job status.",
            "progress": 0,
            "stage": "status_read_error",
            "step": "status_read_error",
            "error": str(exc),
        }


def update_job(job_id: str, **fields: Any) -> Dict[str, Any]:
    current = get_job_status(job_id)
    if current.get("state") == "missing":
        raise FileNotFoundError(f"Job {job_id} does not exist")

    current.update(fields)
    current["updated_at"] = utc_now_iso()
    current = normalise_status_payload(current)

    atomic_write_json(status_path(job_id), current)
    return current


def mark_job_started(job_id: str) -> Dict[str, Any]:
    current = get_job_status(job_id)
    now = utc_now_iso()

    return update_job(
        job_id,
        state="running",
        status="running",
        message="Job is running.",
        stage="starting",
        step="starting",
        started_at=current.get("started_at") or now,
        error=None,
        traceback=None,
    )


def mark_job_completed(job_id: str, demo_path: Optional[str] = None) -> Dict[str, Any]:
    return update_job(
        job_id,
        state="complete",
        status="complete",
        message="Job completed successfully.",
        progress=100,
        stage="complete",
        step="complete",
        demo_path=demo_path,
        finished_at=utc_now_iso(),
        error=None,
        traceback=None,
    )


def mark_job_failed(job_id: str, error: str, traceback_text: Optional[str] = None) -> Dict[str, Any]:
    return update_job(
        job_id,
        state="failed",
        status="failed",
        message="Job failed.",
        stage="failed",
        step="failed",
        error=error,
        traceback=traceback_text,
        finished_at=utc_now_iso(),
    )


def update_status(job_dir: Path, **fields: Any) -> Dict[str, Any]:
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)

    path = status_path_from_job_dir(job_dir)
    job_id = job_dir.name

    if path.exists():
        try:
            current = read_json_file(path)
        except Exception:
            current = default_status_payload(job_id=job_id)
    else:
        current = default_status_payload(job_id=job_id)

    current.update(fields)

    if "status" in fields and "state" not in fields:
        current["state"] = fields["status"]

    if "state" in fields and "status" not in fields:
        current["status"] = fields["state"]

    if "stage" in fields and "step" not in fields:
        current["step"] = fields["stage"]

    if "step" in fields and "stage" not in fields:
        current["stage"] = fields["step"]

    if current.get("status") == "running" and not current.get("started_at"):
        current["started_at"] = utc_now_iso()

    if current.get("status") in {"complete", "failed"} and not current.get("finished_at"):
        current["finished_at"] = utc_now_iso()

    current["updated_at"] = utc_now_iso()
    current = normalise_status_payload(current)

    atomic_write_json(path, current)
    return current


def list_recent_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    runs_dir = ensure_runs_dir()
    jobs: List[Dict[str, Any]] = []

    for child in runs_dir.iterdir():
        if not child.is_dir():
            continue

        status_file = child / "status.json"
        if not status_file.exists():
            continue

        try:
            data = read_json_file(status_file)
            jobs.append(normalise_status_payload(data))
        except Exception:
            continue

    def sort_key(item: Dict[str, Any]) -> str:
        return item.get("updated_at") or item.get("created_at") or ""

    jobs.sort(key=sort_key, reverse=True)
    return jobs[:limit]