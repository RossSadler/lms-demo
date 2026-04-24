import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from pipeline.status import update_status


HEYGEN_API_BASE = "https://api.heygen.com"
HEYGEN_CREATE_ENDPOINT = f"{HEYGEN_API_BASE}/v1/video.webm"
HEYGEN_STATUS_ENDPOINT = f"{HEYGEN_API_BASE}/v1/video_status.get"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _headers() -> dict[str, str]:
    api_key = os.getenv("HEYGEN_API_KEY", "").strip()
    if not api_key:
        raise ValueError("HEYGEN_API_KEY missing")

    return {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }


def build_intro_script(
    *,
    course_title: str,
    course_summary: str,
    lesson_count: int,
) -> str:
    summary = (course_summary or "").strip()
    summary = " ".join(summary.split())

    if len(summary) > 240:
        summary = summary[:237].rstrip() + "..."

    return (
        f"Welcome.\n\n"
        f"In this course, {course_title}, you will get a clear introduction to the key ideas and practical takeaways.\n\n"
        f"This course includes {lesson_count} lesson"
        f"{'' if lesson_count == 1 else 's'}, designed to help you move through the material in a simple, structured way.\n\n"
        f"{summary}\n\n"
        f"Let's begin."
    )


def build_intro_payload(
    *,
    script: str,
    avatar_id: str,
    voice_id: str,
    avatar_style: str = "normal",
) -> dict[str, Any]:
    return {
        "avatar_pose_id": avatar_id,
        "avatar_style": avatar_style,
        "input_text": script,
        "voice_id": voice_id,
    }


def _download_file(url: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)


def _poll_video_status(
    *,
    video_id: str,
    timeout_seconds: int,
    poll_interval: float = 5.0,
) -> dict[str, Any]:
    start = time.time()

    while True:
        response = requests.get(
            HEYGEN_STATUS_ENDPOINT,
            headers=_headers(),
            params={"video_id": video_id},
            timeout=60,
        )
        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            raise ValueError(f"Unexpected HeyGen status response: {data}")

        if data.get("code") != 100:
            raise ValueError(f"HeyGen status error: {data}")

        payload = data.get("data") or {}
        status = (payload.get("status") or "").lower()

        if status in {"completed", "complete", "success"}:
            return data

        if status in {"failed", "error"}:
            raise ValueError(f"HeyGen video generation failed: {data}")

        if time.time() - start > timeout_seconds:
            raise TimeoutError(f"Timed out waiting for HeyGen video {video_id}")

        time.sleep(poll_interval)


def _extract_video_url(status_response: dict[str, Any]) -> str | None:
    payload = status_response.get("data") or {}

    candidate_keys = [
        "video_url",
        "url",
        "download_url",
        "downloadUrl",
    ]

    for key in candidate_keys:
        value = payload.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value

    video_info = payload.get("video")
    if isinstance(video_info, dict):
        for key in candidate_keys:
            value = video_info.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value

    return None


def generate_intro_video(
    *,
    job_dir: Path,
    course_title: str,
    course_summary: str,
    lesson_count: int,
) -> dict[str, Any]:
    if not _env_bool("HEYGEN_ENABLED", default=False):
        return {
            "enabled": False,
            "video_path": None,
            "script_path": None,
            "create_response_path": None,
            "status_response_path": None,
            "video_id": None,
            "message": "HeyGen disabled.",
        }

    avatar_id = os.getenv("HEYGEN_AVATAR_ID", "").strip()
    voice_id = os.getenv("HEYGEN_VOICE_ID", "").strip()
    avatar_style = os.getenv("HEYGEN_AVATAR_STYLE", "normal").strip() or "normal"
    timeout_seconds = int(os.getenv("HEYGEN_TIMEOUT_SECONDS", "300"))

    if not avatar_id:
        raise ValueError("HEYGEN_AVATAR_ID missing")

    if not voice_id:
        raise ValueError("HEYGEN_VOICE_ID missing")

    output_dir = Path(job_dir) / "output"
    json_dir = output_dir / "json"
    video_dir = output_dir / "video"

    json_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    script = build_intro_script(
        course_title=course_title,
        course_summary=course_summary,
        lesson_count=lesson_count,
    )

    payload = build_intro_payload(
        script=script,
        avatar_id=avatar_id,
        voice_id=voice_id,
        avatar_style=avatar_style,
    )

    script_path = json_dir / "course_intro.json"
    create_response_path = json_dir / "heygen_intro_create_response.json"
    status_response_path = json_dir / "heygen_intro_status_response.json"
    video_path = video_dir / "intro.webm"

    script_path.write_text(
        json.dumps(
            {
                "course_title": course_title,
                "course_summary": course_summary,
                "lesson_count": lesson_count,
                "script": script,
                "avatar_id": avatar_id,
                "voice_id": voice_id,
                "avatar_style": avatar_style,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    update_status(
        job_dir=job_dir,
        stage="video_intro",
        message="Submitting HeyGen intro video request.",
    )

    create_response = requests.post(
        HEYGEN_CREATE_ENDPOINT,
        headers=_headers(),
        json=payload,
        timeout=120,
    )
    create_response.raise_for_status()

    create_data = create_response.json()
    create_response_path.write_text(
        json.dumps(create_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if create_data.get("code") != 100:
        raise ValueError(f"Unexpected HeyGen create response: {create_data}")

    video_id = ((create_data.get("data") or {}).get("video_id") or "").strip()
    if not video_id:
        raise ValueError(f"HeyGen create response missing video_id: {create_data}")

    update_status(
        job_dir=job_dir,
        stage="video_intro_polling",
        message="Waiting for HeyGen intro video to finish rendering.",
    )

    status_data = _poll_video_status(
        video_id=video_id,
        timeout_seconds=timeout_seconds,
        poll_interval=5.0,
    )

    status_response_path.write_text(
        json.dumps(status_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    video_url = _extract_video_url(status_data)
    if not video_url:
        raise ValueError(f"HeyGen status response missing video URL: {status_data}")

    update_status(
        job_dir=job_dir,
        stage="video_intro_downloading",
        message="Downloading HeyGen intro video.",
    )

    _download_file(video_url, video_path)

    update_status(
        job_dir=job_dir,
        stage="video_intro_complete",
        message="HeyGen intro video saved.",
    )

    return {
        "enabled": True,
        "video_path": str(video_path),
        "script_path": str(script_path),
        "create_response_path": str(create_response_path),
        "status_response_path": str(status_response_path),
        "video_id": video_id,
        "message": "Intro video generated.",
    }