from pipeline.lifter_export import export_to_wordpress

# IMPORTANT:
# This must point to the run folder that contains:
# - output/json/all_lessons.json
# - output/images/lesson_1.png etc
# - output/audio/lesson_1.mp3 etc

export_to_wordpress(
    "runs/fd014e4150e8/output/json/all_lessons.json"
)