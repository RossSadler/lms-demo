import os
import json
import re
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv()

WP_URL = os.getenv("WP_URL")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")

if not WP_URL:
    raise ValueError("WP_URL missing from .env")

if not WP_USERNAME:
    raise ValueError("WP_USERNAME missing from .env")

if not WP_APP_PASSWORD:
    raise ValueError("WP_APP_PASSWORD missing from .env")


def load_lessons(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def clean_title(value):
    value = str(value or "").strip()
    value = re.sub(r"\s+", " ", value)
    value = value.replace("_", " ").replace("-", " ")
    value = re.sub(r"\s+", " ", value).strip()

    if not value:
        return "Generated Training Course"

    return value.title()


def derive_course_title(lessons, fallback_title=None):
    if fallback_title:
        return clean_title(fallback_title)

    if lessons:
        first = lessons[0] or {}
        title = str(first.get("lesson_title") or "").strip()
        if title:
            title = re.sub(r"^Understanding\s+", "", title, flags=re.IGNORECASE)
            title = re.sub(r"^Introduction\s+to\s+", "", title, flags=re.IGNORECASE)
            return clean_title(title)

    return "Generated Training Course"


def create_llms_resource(endpoint, data):
    url = f"{WP_URL.rstrip('/')}/wp-json/{endpoint.lstrip('/')}"

    response = requests.post(
        url,
        json=data,
        auth=HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD),
    )

    if response.status_code not in (200, 201):
        print("❌ Failed:", response.status_code)
        print(response.text)
        return None

    return response.json()


def upload_media(file_path):
    url = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/media"
    filename = os.path.basename(file_path)
    ext = os.path.splitext(filename)[1].lower()

    content_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".mp4": "video/mp4",
    }

    content_type = content_types.get(ext, "application/octet-stream")

    with open(file_path, "rb") as f:
        response = requests.post(
            url,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": content_type,
            },
            data=f,
            auth=HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD),
        )

    if response.status_code not in (200, 201):
        print("❌ Media upload failed:", response.status_code)
        print(response.text)
        return None

    return response.json().get("source_url")


def format_lesson_body(text):
    if not text:
        return ""

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    html = []
    bullet_items = []

    for i, paragraph in enumerate(paragraphs):
        if paragraph.startswith("- "):
            bullet_items.append(paragraph.replace("- ", "", 1).strip())
            continue

        if bullet_items:
            html.append("<ul>")
            for item in bullet_items:
                html.append(f"<li>{item}</li>")
            html.append("</ul>")
            bullet_items = []

        if i == 0:
            html.append(
                f"""
<div style="font-size:1.08em; line-height:1.65; margin-bottom:22px;">
  <strong>{paragraph}</strong>
</div>
""".strip()
            )
            continue

        if len(paragraph) > 220:
            sentences = [s.strip() for s in paragraph.split(". ") if s.strip()]
            for sentence in sentences:
                if not sentence.endswith("."):
                    sentence += "."
                html.append(f"<p>{sentence}</p>")
        else:
            html.append(f"<p>{paragraph}</p>")

    if bullet_items:
        html.append("<ul>")
        for item in bullet_items:
            html.append(f"<li>{item}</li>")
        html.append("</ul>")

    return "\n".join(html)


def build_lesson_content(lesson, job_dir, index):
    raw_body = lesson.get("lesson_body") or ""
    lesson_body = format_lesson_body(raw_body)

    lesson_body = f"""
<h3 style="margin-bottom:14px;">Overview</h3>
{lesson_body}
""".strip()

    image_path = lesson.get("image")
    audio_path = lesson.get("audio")

    image_url = None
    audio_url = None
    video_url = None

    if index == 1:
        intro_video_path = os.path.abspath(
            os.path.join(job_dir, "output", "video", "intro.mp4")
        )

        print(f"🎬 Looking for intro video: {intro_video_path}")

        if os.path.exists(intro_video_path):
            print("⬆️ Uploading intro video for lesson 1...")
            video_url = upload_media(intro_video_path)
        else:
            print("⚠️ Intro video not found. Lesson 1 will continue without video.")

    if image_path and not video_url:
        clean_image_path = image_path.replace("\\", "/")
        full_image_path = os.path.abspath(os.path.join(job_dir, clean_image_path))

        print(f"🖼️ Looking for image: {full_image_path}")

        if os.path.exists(full_image_path):
            print(f"⬆️ Uploading image for lesson {index}...")
            image_url = upload_media(full_image_path)
        else:
            print(f"❌ Image NOT found: {full_image_path}")

    if audio_path:
        clean_audio_path = audio_path.replace("\\", "/")
        full_audio_path = os.path.abspath(os.path.join(job_dir, clean_audio_path))

        if os.path.exists(full_audio_path):
            print(f"⬆️ Uploading audio for lesson {index}...")
            audio_url = upload_media(full_audio_path)
        else:
            print(f"⚠️ Audio file not found for lesson {index}: {full_audio_path}")

    if video_url:
        lesson_body = f"""
<div style="margin-bottom:28px;">
  <p style="font-weight:700; font-size:1.05em; margin-bottom:12px;">🎬 Course Introduction</p>
  [video src="{video_url}"]
</div>
{lesson_body}
""".strip()

    elif image_url:
        lesson_body = f"""
<div style="margin-bottom:24px;">
  <img src="{image_url}" style="width:100%; border-radius:12px; display:block;" />
</div>
{lesson_body}
""".strip()

    if audio_url and "[audio" not in lesson_body:
        print("🎧 Audio URL:", audio_url)

        lesson_body += f"""
<div style="margin-top:28px;">
  <p style="font-weight:600; margin-bottom:8px;">🎧 Listen to this lesson</p>
  [audio src="{audio_url}"]
</div>
""".strip()

    lesson_body += "<div style='margin-top:30px;'></div>"

    return lesson_body


def export_to_wordpress(json_path, course_title=None):
    lessons = load_lessons(json_path)

    if not lessons:
        print("❌ No lessons found")
        return {
            "ok": False,
            "error": "No lessons found",
        }

    job_dir = os.path.abspath(os.path.join(os.path.dirname(json_path), "..", ".."))
    final_course_title = derive_course_title(lessons, course_title)

    print(f"📦 Creating LifterLMS course: {final_course_title}")
    print(f"📦 Lesson count: {len(lessons)}")

    course_data = {
        "title": final_course_title,
        "content": "<p>This course has been automatically generated from source material and structured into guided lessons with clear progression.</p>",
        "status": "publish",
    }

    course = create_llms_resource("llms/v1/courses", course_data)

    if not course:
        print("❌ Course creation failed")
        return {
            "ok": False,
            "error": "Course creation failed",
        }

    course_id = course.get("id")
    print(f"✅ LifterLMS course created: {course_id}")

    section_data = {
        "title": "Course Content",
        "parent_id": course_id,
        "order": 1,
    }

    section = create_llms_resource("llms/v1/sections", section_data)

    if not section:
        print("❌ Section creation failed")
        return {
            "ok": False,
            "error": "Section creation failed",
            "course_id": course_id,
            "course_title": final_course_title,
        }

    section_id = section.get("id")
    print(f"✅ Section created: {section_id}")

    lesson_ids = []

    for index, lesson in enumerate(lessons, start=1):
        lesson_title = lesson.get("lesson_title") or f"Lesson {index}"
        lesson_body = build_lesson_content(lesson, job_dir, index)

        lesson_data = {
            "title": lesson_title,
            "content": lesson_body,
            "status": "publish",
            "course_id": course_id,
            "parent_id": section_id,
            "order": index,
        }

        created_lesson = create_llms_resource("llms/v1/lessons", lesson_data)

        if created_lesson:
            lesson_id = created_lesson.get("id")
            lesson_ids.append(lesson_id)
            print(f"✅ Lesson created: {lesson_id} - {lesson_title}")
        else:
            print(f"❌ Failed lesson: {lesson_title}")

    print("🎉 LifterLMS export complete")
    print(f"Course title: {final_course_title}")
    print(f"Course ID: {course_id}")
    print(f"Section ID: {section_id}")
    print(f"Lesson IDs: {lesson_ids}")

    course_edit_url = f"{WP_URL.rstrip()}/wp-admin/post.php?post={course_id}&action=edit"
    course_view_url = course.get("link") or f"{WP_URL.rstrip()}"

    return {
        "ok": True,
        "course_id": course_id,
        "course_title": final_course_title,
        "section_id": section_id,
        "lesson_ids": lesson_ids,
        "lesson_count": len(lesson_ids),
        "course_edit_url": course_edit_url,
        "course_view_url": course_view_url,
    }