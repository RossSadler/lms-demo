import json
import shutil
from pathlib import Path

from pipeline.status import update_status


def copy_file(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Missing file: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_folder_contents_safe(src_dir: Path, dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)

    if not src_dir.exists():
        return

    for item in src_dir.iterdir():
        target = dst_dir / item.name

        try:
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
        except Exception:
            continue


def load_lessons_safe(src_json: Path) -> list[dict]:
    if not src_json.exists():
        return []

    try:
        with src_json.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return data

        return []
    except Exception:
        return []


def rewrite_asset_path(value: str) -> str:
    value = value.replace("\\", "/")
    filename = Path(value).name

    if "audio" in value:
        return f"assets/audio/{filename}"

    if "image" in value or "images" in value:
        return f"assets/images/{filename}"

    if "video" in value:
        return f"assets/video/{filename}"

    return value


def rewrite_json_paths(data):
    if isinstance(data, list):
        return [rewrite_json_paths(item) for item in data]

    if isinstance(data, dict):
        rewritten = {}

        for key, value in data.items():
            if isinstance(value, str) and key.lower() in {"audio", "image", "video"}:
                rewritten[key] = rewrite_asset_path(value)
            elif isinstance(value, dict):
                rewritten[key] = rewrite_json_paths(value)
            elif isinstance(value, list):
                rewritten[key] = rewrite_json_paths(value)
            else:
                rewritten[key] = value

        return rewritten

    return data


def find_intro_video_path(src_video_dir: Path) -> str | None:
    intro_video = src_video_dir / "intro.mp4"

    if intro_video.exists():
        return "assets/video/intro.mp4"

    candidates = sorted(src_video_dir.glob("*.mp4"))

    if not candidates:
        return None

    return f"assets/video/{candidates[0].name}"


def inject_intro_video_into_first_lesson(
    lessons: list[dict],
    intro_video_path: str | None,
) -> list[dict]:
    if not lessons:
        return lessons

    first_lesson = dict(lessons[0])
    first_lesson["video"] = intro_video_path
    lessons[0] = first_lesson

    for lesson in lessons[1:]:
        lesson.setdefault("video", None)

    return lessons


def build_html_with_embedded_json(
    src_html: Path,
    dist_dir: Path,
    lessons_data: list[dict],
) -> None:
    html_template = src_html.read_text(encoding="utf-8")
    json_blob = json.dumps(lessons_data, indent=2, ensure_ascii=False)

    if "__LESSON_DATA__" not in html_template:
        raise ValueError("demo/index.html is missing the __LESSON_DATA__ placeholder")

    final_html = html_template.replace("__LESSON_DATA__", json_blob)

    (dist_dir / "index.html").write_text(
        final_html,
        encoding="utf-8",
    )


def build_demo(job_dir: Path) -> str | None:
    job_dir = Path(job_dir)
    root = Path(__file__).resolve().parent.parent

    update_status(
        job_dir=job_dir,
        stage="building_demo",
        message="Building demo package.",
    )

    demo_dir = root / "demo"
    output_dir = job_dir / "output"
    dist_dir = job_dir / "dist"

    src_html = demo_dir / "index.html"
    src_css = demo_dir / "styles.css"
    src_js = demo_dir / "app.js"

    src_json = output_dir / "json" / "all_lessons.json"
    src_audio_dir = output_dir / "audio"
    src_images_dir = output_dir / "images"
    src_video_dir = output_dir / "video"

    dist_audio_dir = dist_dir / "assets" / "audio"
    dist_images_dir = dist_dir / "assets" / "images"
    dist_video_dir = dist_dir / "assets" / "video"

    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    dist_dir.mkdir(parents=True, exist_ok=True)
    dist_audio_dir.mkdir(parents=True, exist_ok=True)
    dist_images_dir.mkdir(parents=True, exist_ok=True)
    dist_video_dir.mkdir(parents=True, exist_ok=True)

    copy_file(src_css, dist_dir / "styles.css")
    copy_file(src_js, dist_dir / "app.js")
    copy_file(src_html, dist_dir / "_template.html")

    copy_folder_contents_safe(src_audio_dir, dist_audio_dir)
    copy_folder_contents_safe(src_images_dir, dist_images_dir)
    copy_folder_contents_safe(src_video_dir, dist_video_dir)

    lessons = load_lessons_safe(src_json)
    lessons = rewrite_json_paths(lessons)

    intro_video_path = find_intro_video_path(src_video_dir)
    lessons = inject_intro_video_into_first_lesson(
        lessons,
        intro_video_path,
    )

    build_html_with_embedded_json(
        dist_dir / "_template.html",
        dist_dir,
        lessons,
    )

    (dist_dir / "_template.html").unlink(missing_ok=True)

    update_status(
        job_dir=job_dir,
        stage="demo_ready",
        message="Demo build complete.",
    )

    return str(dist_dir)