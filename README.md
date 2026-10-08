# AI Career Guide & Resume Analyzer

A Flask web application that helps students and early-career job seekers prepare
career plans, review resumes, compare resumes with job descriptions, and
practice interviews.

## Features

- Consent-gated AI career plans and role-focused learning roadmaps.
- Resume upload and parsing for PDF, DOCX, and TXT, with resume-health feedback
  and a **rule-based ATS compatibility estimate**.
- Deterministic job-description keyword estimate and structured resume-to-JD
  matching when resume text is supplied.
- Interview practice in technical, HR, behavioral, coding, and mixed modes.
  Question generation and answer evaluation use the configured AI provider
  after consent; malformed AI evaluation output uses a deterministic heuristic
  fallback.
- Interview summaries, weak-area review, and a generic seven-day practice plan.
- Browser-local dashboard and PDF report export.
- Browser speech-to-text input where the browser supports the Web Speech API.

The resume ATS score and JD keyword estimate are heuristics, not AI-generated
scores or official employer ATS results. Structured resume-to-JD dimensions
remain unassessed when the available profile data is insufficient. Career
readiness is an AI-generated estimate, not a hiring or placement prediction.
Interview report dimensions include locally derived estimates; they are not
all independent AI evaluations.

There are no live job-search APIs, LinkedIn or GitHub profile auditors, salary
forecasting, user accounts, authentication, or server-side multi-user storage.

## Tech stack

- Python 3.13, Flask, and Werkzeug.
- HTML, CSS, and vanilla JavaScript.
- Google Gemini through the server-side AI provider interface.
- JSON files for role and skill catalogs.
- PyPDF2, python-docx, and ReportLab.
- pytest and Node's built-in test runner.

## Project structure

```text
.
├── app.py                  # Flask routes, configuration, and response handling
├── wsgi.py                 # WSGI entry point
├── Procfile                # Linux-host web process command
├── requirements.txt        # Pinned Python dependencies
├── .env.example            # Placeholder environment configuration
├── .gitignore
├── README.md
├── data/                   # Static JSON catalogs
├── services/               # Parsing, analysis, matching, and AI provider code
│   └── ai/
├── templates/              # Flask/Jinja pages
├── public/static/           # CSS, JavaScript, and assets served by Vercel
├── tests/                  # Python and Node tests
└── reports/                # Reserved/ignored generated report directory
```

## Local installation

Use the existing project virtual environment if it is already present. On
Windows:

```bash
venv\Scripts\activate
pip install -r requirements.txt
```

On Linux or macOS:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

If no project environment exists, create one using `python -m venv venv`
(Linux/macOS) or `py -m venv venv` (Windows), then activate it and install
`requirements.txt`. Do not create another environment when the project `venv`
is already available.

## Environment variables

Create a `.env` file in the project root using the example:

```env
APP_ENV=development
AI_PROVIDER=gemini
GEMINI_API_KEY=your_api_key_here
SECRET_KEY=replace_with_a_long_random_secret
PORT=5000
AI_RATE_LIMIT_WINDOW_SECONDS=60
AI_RATE_LIMIT_MAX_REQUESTS=10
TRUSTED_PROXY_COUNT=0
```

In development, if `SECRET_KEY` is omitted, the app creates an ephemeral key
for that process. Production startup fails when `SECRET_KEY` is missing. Never
commit credentials or expose them in frontend code.

In production, configure `APP_ENV=production`, `AI_PROVIDER=gemini`, a
server-side `GEMINI_API_KEY`, and a strong private `SECRET_KEY` on the hosting
platform. The platform supplies `PORT`. Do not put real credentials in this
file, source code, or frontend assets. Keep the rate-limit settings at their
reviewed defaults unless the deployment has an explicit capacity policy. Set
`TRUSTED_PROXY_COUNT` only when requests are received through a known trusted
proxy chain, and use the exact number of trusted hops; the default `0` ignores
forwarded client and protocol headers. HSTS is enabled only for secure
production requests.

## Run locally

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000/
```

## Production / deployment

For a Linux Python host such as Render, use the WSGI entry point. Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
APP_ENV=production gunicorn wsgi:app --bind 0.0.0.0:$PORT
```

The `Procfile` contains the production Gunicorn command. Gunicorn runs the
application; `python app.py` is only for local development.

AI request limits are kept in process-local memory. Gunicorn workers do not
share counters, so limits are enforced independently by each worker. A shared
external rate-limit store would be needed for stronger distributed enforcement.
For a deployment behind a trusted reverse proxy, set `TRUSTED_PROXY_COUNT` to
the exact number of trusted proxies that append to `X-Forwarded-For` (for a
single Render edge proxy, use `1`). It defaults to `0`, which ignores forwarded
headers. Configure this only when direct access that bypasses the trusted proxy
is prevented; do not set it based on untrusted client-supplied headers. The
configured hop count also trusts `X-Forwarded-Proto` from those same proxies so
production HTTPS detection and HSTS work behind TLS termination.

For Vercel, the Flask application is detected from the exported `app` in
`app.py` (also re-exported by `wsgi.py`); a `vercel.json` file is not required.
Vercel serves assets from `public/`, while Flask templates continue to reference
them at `/static/`. Resume uploads are written to the system temporary directory
and removed after processing; temporary storage is not persistent across function
invocations. Configure `APP_ENV=production`, a strong `SECRET_KEY`, and
`AI_PROVIDER=gemini` / `GEMINI_API_KEY` privately in the Vercel project settings.
The in-memory AI rate limiter is per function instance and is not a shared
deployment-wide limit.

PDF report requests are validated and limited to 1 MiB of JSON; generated PDFs
are limited to 10 MiB. Responses include a compatible Content Security Policy,
frame protection, and privacy-oriented referrer policy. HSTS is sent only for
secure requests in production; behind a trusted TLS-terminating proxy, configure
the trusted proxy count so Flask can identify the original HTTPS scheme.

## Data storage and deployment prerequisites

There is no database, user authentication, or server-side multi-user account
store. Role and skill catalogs are static JSON files in `data/`. Career plans,
resume analysis, job-match results, interview reports, and roadmap progress are
saved in the user's browser `localStorage`; clearing browser storage removes
those saved results. Resume uploads are placed in the server's `uploads/`
directory only while being processed and are removed afterward. PDF reports
are generated for the response and are not persisted by the export endpoint.
Interview state in browser storage may include answers entered during practice.
Career-plan and interview AI requests send their relevant submitted content to
the configured Gemini provider only after the required AI consent is supplied.

Deployment requires a Linux-compatible Python runtime, dependencies from
`requirements.txt`, the production environment variables above, and the
platform-provided `PORT`. Use the WSGI/Gunicorn command above; the Flask
development server is for local development only.

## Testing

```bash
python -m pytest -q
python -m compileall .
node --check public/static/js/main.js
node --check public/static/js/job-description.js
node --check public/static/js/interview.js
node --check public/static/js/dashboard.js
node --check public/static/js/career.js
node --check public/static/js/resume.js
node --test tests/pdf-download.test.js tests/dashboard.test.js
```

## Health check

```text
GET /health
```

Response:

```json
{
  "status": "ok"
}
```

## Known limitations

- AI rate-limit counters are process-local. Separate Gunicorn workers do not
  share counters; distributed enforcement would require a shared external
  store.
- There is no database, authentication, or server-side user account store.
- Career plans, resume-analysis results, job-match results, interview reports,
  and roadmap progress are stored in the user's browser `localStorage`.
  Interview state can include practice answers; clearing browser storage
  removes saved results.
- Role and skill catalogs are static JSON. There are no live job-market or
  salary data integrations.
- Resume uploads have a 5 MiB size limit, PDF files are limited to 25 pages,
  extracted text to 100,000 characters, and DOCX archive expansion is bounded.
  Job descriptions are limited to 50,000 characters.
- PDF export input is limited to 1 MiB and generated PDFs to 10 MiB.
- AI-dependent functionality requires a valid Gemini configuration. The API
  key remains server-side; career-plan and interview AI requests require
  explicit user consent.

## Screenshots

Add screenshots here after running the app locally.

## License

This project is provided as a learning and portfolio project. Update the license if you plan to distribute it publicly.
