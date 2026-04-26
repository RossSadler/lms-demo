import base64
import io
import json
import os
import random
import time
import traceback
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from docx import Document
from elevenlabs.client import ElevenLabs
from openai import OpenAI
from PIL import Image

from pipeline.heygen_intro import generate_intro_video
from pipeline.status import update_status


load_dotenv()


OPENAI_MODEL = os.getenv("OPENAI_LESSON_MODEL", "gpt-4.1-mini")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")

OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "4"))
ELEVENLABS_MAX_RETRIES = int(os.getenv("ELEVENLABS_MAX_RETRIES", "4"))
IMAGE_MAX_RETRIES = int(os.getenv("IMAGE_MAX_RETRIES", "3"))

RETRY_BASE_DELAY = float(os.getenv("RETRY_BASE_DELAY", "2.0"))
RETRY_MAX_DELAY = float(os.getenv("RETRY_MAX_DELAY", "20.0"))


def run_job(job_id: str, job_dir: str, input_path: str, options: dict | None = None) -> dict:
    """
    Background entrypoint expected by app.py.
    """
    job_dir_path = Path(job_dir)
    input_path_path = Path(input_path)

    result = run_pipeline(
        job_dir=job_dir_path,
        input_path=input_path_path,
        options=options or {},
    )

    demo_path = None
    dist_dir = job_dir_path / "dist"
    if dist_dir.exists():
        demo_path = str(dist_dir)

    return {
        "ok": True,
        "job_id": job_id,
        "demo_path": demo_path,
        "video": result.get("video"),
    }


def extract_paragraphs(filepath: Path) -> list[str]:
    doc = Document(str(filepath))
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]


def split_into_sections(paragraphs: list[str]) -> list[str]:
    sections = []
    current_section = []

    for para in paragraphs:
        is_article = para.startswith("ARTICLE")
        is_heading = para.isupper()
        is_definition = para in [
            "About ARPIM",
            "About the ARPIM Code",
            "Definitions",
        ]

        if is_article or is_heading or is_definition:
            if current_section:
                sections.append("\n\n".join(current_section))
                current_section = []

        current_section.append(para)

    if current_section:
        sections.append("\n\n".join(current_section))

    return sections


def extract_json_from_text(text: str) -> dict:
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start:end + 1])

    raise ValueError("Invalid JSON returned by model")


def lesson_prompt(section_text: str) -> str:
    return f"""
You are creating a training lesson from regulatory content.

Rewrite the material so it is:
- clear
- simplified
- suitable for training
- not written like legal text

Create:

1. lesson_title
2. lesson_body
3. audio_script
4. presenter_script

Presenter script rules:
- short lines
- natural pauses
- conversational tone
- varied rhythm
- no long paragraphs

Return ONLY valid JSON:

{{
  "lesson_title": "string",
  "lesson_body": "string",
  "audio_script": "string",
  "presenter_script": "string"
}}

Source text:
{section_text[:2000]}
""".strip()

def _build_intro_from_lesson(json_dir: Path) -> str:
    lesson_1_path = json_dir / "lesson_1.json"

    if not lesson_1_path.exists():
        return "Welcome. Let's begin."

    lesson = json.loads(lesson_1_path.read_text(encoding="utf-8"))

    presenter = lesson.get("presenter_script", "").strip()

    intro = (
        "Welcome to this training module.\n\n"
        "In this course, we’ll walk through the key concepts step by step.\n\n"
        "Let’s begin.\n\n"
    )

    return intro + presenter

def build_image_prompt(lesson: dict) -> str:
    return f"""
Create a realistic photo-style training visual for a professional compliance e-learning course.

The image must depict a specific workplace moment from the lesson, not a generic corporate stock photo.

Lesson title:
{lesson['lesson_title']}

Lesson content:
{lesson['lesson_body'][:1000]}

Create a single believable scene that shows:
- the key decision, risk, mistake, or compliance issue described in the lesson
- professionals dealing with a real situation, not posing for the camera
- clear visual storytelling through body language, setting, documents, devices, or interaction
- a pharmaceutical, healthcare, office, conference, or training-relevant environment where appropriate

Style requirements:
- realistic photographic style
- natural lighting
- documentary / training scenario feel
- professional but not glossy or promotional
- no generic handshake imagery
- no smiling stock-photo group poses
- no abstract concepts
- no floating icons
- no illustrations
- no cartoons
- no visible text
- no logos
- no watermarks

Composition:
- landscape format
- one clear focal point
- realistic depth of field
- suitable as a supporting image in an LMS lesson
- should feel purposeful, practical, and directly linked to the lesson topic
""".strip()


def save_image_from_b64(b64_data: str, output_path: Path) -> None:
    image_bytes = base64.b64decode(b64_data)
    image = Image.open(io.BytesIO(image_bytes))
    image.save(output_path, format="PNG")


def combine_all_lessons(json_dir: Path) -> None:
    lesson_files = sorted(
        [
            p for p in json_dir.glob("lesson_*.json")
            if p.stem.replace("lesson_", "").isdigit()
        ],
        key=lambda p: int(p.stem.replace("lesson_", "")),
    )

    combined_lessons = []
    for lesson_file in lesson_files:
        combined_lessons.append(
            json.loads(lesson_file.read_text(encoding="utf-8"))
        )

    (json_dir / "all_lessons.json").write_text(
        json.dumps(combined_lessons, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def save_lesson_json(lesson_path: Path, lesson: dict) -> None:
    lesson_path.write_text(
        json.dumps(lesson, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def save_error_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def compute_backoff(attempt: int) -> float:
    raw = RETRY_BASE_DELAY * (2 ** (attempt - 1))
    capped = min(raw, RETRY_MAX_DELAY)
    jitter = random.uniform(0, 0.75)
    return capped + jitter


def retry_call(
    fn,
    *,
    max_retries: int,
    retry_label: str,
    on_retry=None,
):
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_error = exc

            if attempt >= max_retries:
                raise

            delay = compute_backoff(attempt)

            if on_retry:
                try:
                    on_retry(attempt, delay, exc)
                except Exception:
                    pass

            time.sleep(delay)

    raise last_error


def generate_lesson_with_retry(
    client: OpenAI,
    section_text: str,
    *,
    job_dir: Path,
    lesson_number: int,
    total_lessons: int,
) -> str:
    def _call():
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=lesson_prompt(section_text),
        )
        return response.output_text

    def _on_retry(attempt: int, delay: float, exc: Exception):
        update_status(
            job_dir=job_dir,
            stage="lessons",
            message=(
                f"Retrying lesson {lesson_number} generation "
                f"(attempt {attempt + 1}/{OPENAI_MAX_RETRIES}) after error: {exc}"
            ),
            current_lesson=lesson_number,
            total_lessons=total_lessons,
        )

    return retry_call(
        _call,
        max_retries=OPENAI_MAX_RETRIES,
        retry_label=f"lesson_generation_{lesson_number}",
        on_retry=_on_retry,
    )


def generate_audio_with_retry(
    eleven_client: ElevenLabs,
    voice_id: str,
    text: str,
    *,
    job_dir: Path,
    lesson_number: int,
    total_lessons: int,
):
    def _call():
        return eleven_client.text_to_speech.convert(
            voice_id=voice_id,
            model_id=ELEVENLABS_MODEL,
            text=text,
        )

    def _on_retry(attempt: int, delay: float, exc: Exception):
        update_status(
            job_dir=job_dir,
            stage="audio",
            message=(
                f"Retrying audio for lesson {lesson_number} "
                f"(attempt {attempt + 1}/{ELEVENLABS_MAX_RETRIES}) after error: {exc}"
            ),
            current_lesson=lesson_number,
            total_lessons=total_lessons,
        )

    return retry_call(
        _call,
        max_retries=ELEVENLABS_MAX_RETRIES,
        retry_label=f"audio_generation_{lesson_number}",
        on_retry=_on_retry,
    )


def generate_image_with_retry(
    client: OpenAI,
    lesson: dict,
    *,
    job_dir: Path,
    lesson_number: int,
    total_lessons: int,
):
    def _call():
        return client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=build_image_prompt(lesson),
            size="1536x1024",
        )

    def _on_retry(attempt: int, delay: float, exc: Exception):
        update_status(
            job_dir=job_dir,
            stage="images",
            message=(
                f"Retrying image for lesson {lesson_number} "
                f"(attempt {attempt + 1}/{IMAGE_MAX_RETRIES}) after error: {exc}"
            ),
            current_lesson=lesson_number,
            total_lessons=total_lessons,
        )

    return retry_call(
        _call,
        max_retries=IMAGE_MAX_RETRIES,
        retry_label=f"image_generation_{lesson_number}",
        on_retry=_on_retry,
    )


def build_demo_if_available(job_dir: Path) -> str | None:
    try:
        from pipeline.build_demo import build_demo
    except Exception:
        return None

    try:
        demo_path = build_demo(job_dir)
        if demo_path:
            return str(demo_path)
    except TypeError:
        try:
            demo_path = build_demo(str(job_dir))
            if demo_path:
                return str(demo_path)
        except Exception:
            return None
    except Exception:
        return None

    dist_dir = job_dir / "dist"
    return str(dist_dir) if dist_dir.exists() else None


def _build_course_title_and_summary(json_dir: Path, total_lessons: int) -> tuple[str, str]:
    all_lessons_path = json_dir / "all_lessons.json"

    if all_lessons_path.exists():
        try:
            lessons = json.loads(all_lessons_path.read_text(encoding="utf-8"))
            valid_lessons = [lesson for lesson in lessons if lesson.get("status") != "failed"]

            if valid_lessons:
                first_title = valid_lessons[0].get("lesson_title", "").strip()
                course_title = first_title or "Generated Training Course"

                summary_parts = []
                for lesson in valid_lessons[:3]:
                    title = lesson.get("lesson_title", "").strip()
                    body = lesson.get("lesson_body", "").strip()
                    if title:
                        summary_parts.append(title)
                    elif body:
                        summary_parts.append(body[:180])

                course_summary = " This course covers: " + "; ".join(summary_parts) if summary_parts else (
                    f"This course contains {total_lessons} structured training lessons."
                )
                return course_title, course_summary
        except Exception:
            pass

    return "Generated Training Course", f"This course contains {total_lessons} structured training lessons."


def run_pipeline(job_dir: Path, input_path: Path, options: dict | None = None) -> dict:
    options = options or {}

    run_lessons = bool(options.get("run_lessons", True))
    run_audio = bool(options.get("run_audio", False))
    run_images = bool(options.get("run_images", False))
    run_video = bool(options.get("run_video", False))
    demo_safe_mode = bool(options.get("demo_safe_mode", True))
    batch_size = int(options.get("batch_size", 5))
    max_total_lessons = int(options.get("max_total_lessons", 10))
    fast_mode = bool(options.get("fast_mode", False))

    print("OPTIONS RECEIVED:", options)
    print("RUN AUDIO:", run_audio)
    print("RUN VIDEO:", run_video)

    job_dir = Path(job_dir)
    input_path = Path(input_path)

    output_dir = job_dir / "output"
    json_dir = output_dir / "json"
    audio_dir = output_dir / "audio"
    raw_dir = output_dir / "raw"
    image_dir = output_dir / "images"
    error_dir = output_dir / "errors"

    output_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    error_dir.mkdir(parents=True, exist_ok=True)

    update_status(
        job_dir=job_dir,
        status="running",
        stage="starting",
        message="Pipeline starting.",
        run_audio=run_audio,
        run_images=run_images,
        run_video=run_video,
        fast_mode=fast_mode,
        demo_safe_mode=demo_safe_mode,
        max_total_lessons=max_total_lessons,
        batch_size=batch_size,
    )

    client = OpenAI()

    update_status(
        job_dir=job_dir,
        stage="parsing",
        message="Reading uploaded document.",
    )

    paragraphs = extract_paragraphs(input_path)
    sections = split_into_sections(paragraphs)

    visible_total = max_total_lessons
    total_lessons = min(len(sections), max_total_lessons)

    update_status(
        job_dir=job_dir,
        stage="parsed",
        message=f"Found {len(sections)} sections in document.",
        total_lessons=total_lessons,
    )

    eleven_client = None
    voice_id = None

    if run_audio:
        eleven_api_key = os.getenv("ELEVENLABS_API_KEY")
        voice_id = os.getenv("ELEVENLABS_VOICE_ID")

        if not eleven_api_key:
            raise ValueError("ELEVENLABS_API_KEY missing")

        if not voice_id:
            raise ValueError("ELEVENLABS_VOICE_ID missing")

        eleven_client = ElevenLabs(api_key=eleven_api_key)

    lesson_failures: list[dict[str, Any]] = []
    image_failures: list[dict[str, Any]] = []
    video_result: dict[str, Any] | None = None

    if run_lessons:
        existing = [
            p for p in json_dir.glob("lesson_*.json")
            if p.stem.replace("lesson_", "").isdigit()
        ]
        start_index = len(existing)

        remaining_allowed = max_total_lessons - start_index
        if remaining_allowed <= 0:
            update_status(
                job_dir=job_dir,
                stage="lessons",
                message="Max lesson limit already reached. Skipping lesson generation.",
                completed_lessons=start_index,
                total_lessons=total_lessons,
            )
        else:
            batch_limit = min(batch_size, remaining_allowed, len(sections) - start_index)

            update_status(
                job_dir=job_dir,
                stage="lessons",
                message=f"Generating up to {batch_limit} lessons.",
                current_lesson=start_index + 1 if batch_limit > 0 else start_index,
                completed_lessons=start_index,
                total_lessons=total_lessons,
            )

            for i, section in enumerate(sections[start_index:start_index + batch_limit]):
                n = start_index + i + 1
                lesson_path = json_dir / f"lesson_{n}.json"
                raw_path = raw_dir / f"lesson_{n}.txt"
                lesson_error_path = error_dir / f"lesson_{n}_error.json"

                try:
                    update_status(
                        job_dir=job_dir,
                        stage="lessons",
                        message=f"Generating lesson {n} of {visible_total}.",
                        current_lesson=n,
                        completed_lessons=n - 1,
                        total_lessons=total_lessons,
                    )

                    raw = generate_lesson_with_retry(
                        client,
                        section,
                        job_dir=job_dir,
                        lesson_number=n,
                        total_lessons=total_lessons,
                    )

                    raw_path.write_text(raw, encoding="utf-8")

                    lesson = extract_json_from_text(raw)
                    lesson["audio"] = ""
                    lesson["image"] = ""
                    lesson["lesson_number"] = n
                    lesson["status"] = "ok"

                    save_lesson_json(lesson_path, lesson)

                    update_status(
                        job_dir=job_dir,
                        stage="lessons",
                        message=f"Lesson {n} generated: {lesson['lesson_title']}",
                        current_lesson=n,
                        completed_lessons=n,
                        total_lessons=total_lessons,
                    )

                    if run_audio and eleven_client is not None:
                        try:
                            update_status(
                                job_dir=job_dir,
                                stage="audio",
                                message=f"Generating audio for lesson {n} of {total_lessons}.",
                                current_lesson=n,
                                completed_lessons=n - 1,
                                total_lessons=total_lessons,
                            )

                            audio_stream = generate_audio_with_retry(
                                eleven_client,
                                voice_id,
                                lesson["audio_script"],
                                job_dir=job_dir,
                                lesson_number=n,
                                total_lessons=total_lessons,
                            )

                            audio_path = audio_dir / f"lesson_{n}.mp3"
                            with open(audio_path, "wb") as f:
                                for chunk in audio_stream:
                                    if chunk:
                                        f.write(chunk)

                            lesson["audio"] = str(audio_path.relative_to(job_dir))
                            save_lesson_json(lesson_path, lesson)

                            update_status(
                                job_dir=job_dir,
                                stage="audio",
                                message=f"Audio saved for lesson {n}.",
                                current_lesson=n,
                                completed_lessons=n,
                                total_lessons=total_lessons,
                            )

                            time.sleep(1.5)

                        except Exception as audio_exc:
                            lesson["audio_error"] = str(audio_exc)
                            save_lesson_json(lesson_path, lesson)

                            save_error_json(
                                lesson_error_path,
                                {
                                    "lesson_number": n,
                                    "stage": "audio",
                                    "error": str(audio_exc),
                                    "traceback": traceback.format_exc(),
                                },
                            )

                            update_status(
                                job_dir=job_dir,
                                stage="audio",
                                message=f"Audio failed for lesson {n}, but pipeline is continuing.",
                                current_lesson=n,
                                completed_lessons=n,
                                total_lessons=total_lessons,
                                last_error=str(audio_exc),
                            )

                except Exception as lesson_exc:
                    lesson_failures.append(
                        {
                            "lesson_number": n,
                            "error": str(lesson_exc),
                        }
                    )

                    save_error_json(
                        lesson_error_path,
                        {
                            "lesson_number": n,
                            "stage": "lesson",
                            "error": str(lesson_exc),
                            "traceback": traceback.format_exc(),
                            "section_preview": section[:1000],
                        },
                    )

                    fallback_lesson = {
                        "lesson_number": n,
                        "lesson_title": f"Lesson {n} failed",
                        "lesson_body": "",
                        "audio_script": "",
                        "presenter_script": "",
                        "audio": "",
                        "image": "",
                        "status": "failed",
                        "error": str(lesson_exc),
                    }
                    save_lesson_json(lesson_path, fallback_lesson)

                    update_status(
                        job_dir=job_dir,
                        stage="lessons",
                        message=f"Lesson {n} failed, but pipeline is continuing.",
                        current_lesson=n,
                        completed_lessons=max(0, n - 1),
                        total_lessons=total_lessons,
                        last_error=str(lesson_exc),
                    )

            combine_all_lessons(json_dir)

    if run_images:
        lesson_files = sorted(
            [
                p for p in json_dir.glob("lesson_*.json")
                if p.stem.replace("lesson_", "").isdigit()
            ],
            key=lambda p: int(p.stem.replace("lesson_", "")),
        )

        update_status(
            job_dir=job_dir,
            stage="images",
            message="Starting image generation.",
            total_lessons=total_lessons,
        )

        existing_images = [
            p for p in image_dir.glob("lesson_*.png")
            if p.stem.replace("lesson_", "").isdigit()
        ]
        start_index = len(existing_images)

        for lesson_file in lesson_files[start_index:start_index + batch_size]:
            n = int(lesson_file.stem.replace("lesson_", ""))
            output_path = image_dir / f"lesson_{n}.png"
            image_error_path = error_dir / f"lesson_{n}_image_error.json"

            if output_path.exists():
                continue

            lesson = json.loads(lesson_file.read_text(encoding="utf-8"))

            if lesson.get("status") == "failed":
                continue

            try:
                update_status(
                    job_dir=job_dir,
                    stage="images",
                    message=f"Generating image for lesson {n}.",
                    current_lesson=n,
                    total_lessons=total_lessons,
                )

                result = generate_image_with_retry(
                    client,
                    lesson,
                    job_dir=job_dir,
                    lesson_number=n,
                    total_lessons=total_lessons,
                )

                b64_data = result.data[0].b64_json
                save_image_from_b64(b64_data, output_path)

                lesson["image"] = str(output_path.relative_to(job_dir))
                save_lesson_json(lesson_file, lesson)

                update_status(
                    job_dir=job_dir,
                    stage="images",
                    message=f"Image saved for lesson {n}.",
                    current_lesson=n,
                    total_lessons=total_lessons,
                )

            except Exception as image_exc:
                image_failures.append(
                    {
                        "lesson_number": n,
                        "error": str(image_exc),
                    }
                )

                lesson["image_error"] = str(image_exc)
                save_lesson_json(lesson_file, lesson)

                save_error_json(
                    image_error_path,
                    {
                        "lesson_number": n,
                        "stage": "image",
                        "error": str(image_exc),
                        "traceback": traceback.format_exc(),
                    },
                )

                update_status(
                    job_dir=job_dir,
                    stage="images",
                    message=f"Image failed for lesson {n}, but pipeline is continuing.",
                    current_lesson=n,
                    total_lessons=total_lessons,
                    last_error=str(image_exc),
                )

        combine_all_lessons(json_dir)

    if run_video:
        try:
            existing_video_path = output_dir / "video" / "intro.mp4"

            if existing_video_path.exists():
                video_result = {
                    "enabled": True,
                    "video_path": str(existing_video_path),
                    "script_path": None,
                    "create_response_path": None,
                    "status_response_path": None,
                    "video_id": None,
                    "message": "Intro video already exists. Skipping regeneration.",
                }

                update_status(
                    job_dir=job_dir,
                    stage="video_intro_complete",
                    message="Intro video already exists. Skipping regeneration.",
                )
            else:
                course_title, course_summary = _build_course_title_and_summary(json_dir, total_lessons)

                update_status(
                    job_dir=job_dir,
                    stage="video_intro",
                    message="Starting intro video generation.",
                )

                video_result = generate_intro_video(
                    job_dir=job_dir,
                    course_title=course_title,
                    course_summary=course_summary,
                    lesson_count=total_lessons,
                )

        except Exception as video_exc:
            video_result = {
                "enabled": False,
                "video_path": None,
                "script_path": None,
                "create_response_path": None,
                "status_response_path": None,
                "video_id": None,
                "error": str(video_exc),
                "message": "Intro video skipped or failed.",
            }

            save_error_json(
                error_dir / "video_intro_error.json",
                {
                    "stage": "video_intro",
                    "error": str(video_exc),
                    "traceback": traceback.format_exc(),
                },
            )

            update_status(
                job_dir=job_dir,
                stage="video_intro_failed",
                message="Intro video failed, continuing pipeline because demo-safe mode is enabled.",
                last_error=str(video_exc),
            )

            if not demo_safe_mode:
                raise

    demo_path = None

    update_status(
        job_dir=job_dir,
        status="running",
        stage="pipeline_complete",
        message="Pipeline completed. Building demo.",
        completed_lessons=total_lessons,
        total_lessons=total_lessons,
        lesson_failures=len(lesson_failures),
        image_failures=len(image_failures),
    )

    try:
        demo_path = build_demo_if_available(job_dir)

        update_status(
            job_dir=job_dir,
            status="complete",
            stage="complete",
            message="Pipeline and demo build completed.",
            completed_lessons=total_lessons,
            total_lessons=total_lessons,
            demo_path=demo_path,
            lesson_failures=len(lesson_failures),
            image_failures=len(image_failures),
        )
    except Exception as demo_exc:
        update_status(
            job_dir=job_dir,
            status="complete",
            stage="complete",
            message="Pipeline completed, but demo build failed.",
            completed_lessons=total_lessons,
            total_lessons=total_lessons,
            demo_path=None,
            lesson_failures=len(lesson_failures),
            image_failures=len(image_failures),
            last_error=str(demo_exc),
        )

    return {
        "ok": True,
        "demo_path": demo_path,
        "video": video_result,
        "lesson_failures": lesson_failures,
        "image_failures": image_failures,
    }