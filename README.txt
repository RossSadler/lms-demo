AI Course Generator - Instant Demo Full File Set

Drop these into your project root, keeping the same folders:

- app.py
- templates/index.html
- templates/jobs.html
- templates/progress.html
- templates/result.html
- templates/login.html
- static/app.css
- sample_demo/index.html
- sample_demo/styles.css
- sample_demo/app.js

What changed:
- Adds /demo/sample/ route for an instant, no-upload demo.
- Adds a "Try instant demo" button to the homepage.
- Keeps generated-job demos working at /demo/<job_id>/.
- Keeps login protection in place, so users still need to log in first.

Local test:
1. Stop Flask.
2. Copy files into place.
3. Run: python app.py
4. Visit: http://127.0.0.1:5000
5. Log in.
6. Click "Try instant demo".

Render:
- Commit and push these files.
- Make sure APP_USERNAME, APP_PASSWORD, and FLASK_SECRET_KEY are set in Render environment variables.

To replace the sample later:
- Overwrite the files inside sample_demo/ with a real exported dist course.
- Keep an index.html at sample_demo/index.html.
