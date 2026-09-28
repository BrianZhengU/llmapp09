"""Flask frontend for the LLM API.

Run:  python app.py      ->  http://localhost:5000
The browser talks only to this Flask app; Flask forwards /api/<task> to BACKEND_URL.
"""
import os

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8080").rstrip("/")
BACKEND_TIMEOUT = float(os.getenv("BACKEND_TIMEOUT_SECONDS", "180"))

# Tabs shown in the UI, in order. Each maps to POST {BACKEND_URL}/api/<task>.
TASKS = ["support", "summarize", "generate", "extract", "classify", "sentiment", "intent", "chat"]

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html", tasks=TASKS, backend_url=BACKEND_URL)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/api/<task>")
def proxy(task: str):
    if task not in TASKS:
        return jsonify(detail=f"Unknown task '{task}'"), 404
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/{task}",
            json=request.get_json(silent=True) or {},
            timeout=BACKEND_TIMEOUT,
        )
    except requests.RequestException as exc:
        return jsonify(detail=f"Backend unreachable at {BACKEND_URL}: {exc}"), 502
    return resp.content, resp.status_code, {"Content-Type": resp.headers.get("Content-Type", "application/json")}


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
