import json
from pathlib import Path

from dotenv import load_dotenv

from pipeline.heygen_intro import generate_intro_video

load_dotenv()

job_dir = Path("runs/test_heygen_job")
job_dir.mkdir(parents=True, exist_ok=True)

result = generate_intro_video(
    job_dir=job_dir,
    course_title="Pharmaceutical Compliance Essentials",
    course_summary="A short introduction to the key ideas, rules, and practical expectations covered in this course.",
    lesson_count=5,
)

print(json.dumps(result, indent=2))