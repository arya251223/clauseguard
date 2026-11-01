"""Flask HTTP layer: upload API, report retrieval/export and the static frontend."""
import json
import re
import tempfile
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from app import config, parser
from app.auditor import audit_pdf
from app.llm import LLMError
from app.report import to_markdown

ID_RE = re.compile(r"^[0-9a-f]{32}$")
STATIC = config.BASE_DIR / "static"


def create_app(results_dir: Path = None, gemini=None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_BYTES + 4096
    rdir = Path(results_dir or config.RESULTS_DIR)
    rdir.mkdir(parents=True, exist_ok=True)

    def err(msg, code):
        return jsonify({"error": msg}), code

    def save(report: dict) -> dict:
        rid = uuid.uuid4().hex
        report["id"] = rid
        (rdir / f"{rid}.json").write_text(json.dumps(report))
        return report

    def load(rid: str):
        if not ID_RE.match(rid):
            return None
        f = rdir / f"{rid}.json"
        return json.loads(f.read_text()) if f.exists() else None

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
        return resp

    @app.errorhandler(413)
    def too_big(_):
        return err(f"File too large. Limit is {config.MAX_UPLOAD_BYTES // 1024 // 1024} MB.", 413)

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/static/<path:name>")
    def static_files(name):
        return send_from_directory(STATIC, name)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "pdf_backend": parser.backend_name(),
                        "gemini_configured": bool(config.GEMINI_API_KEY or gemini),
                        "model": config.GEMINI_MODEL})

    def run_audit(path: str, name: str, engine: str):
        try:
            return jsonify(save(audit_pdf(path, name, engine, gemini)))
        except parser.PDFError as e:
            return err(str(e), 422)
        except LLMError as e:
            return err(f"Gemini engine requested but unavailable: {e}", 400)
        except ValueError as e:
            return err(str(e), 400)

    @app.post("/api/audit")
    def audit():
        f = request.files.get("file")
        if not f or not f.filename:
            return err("Attach a PDF in the 'file' field.", 400)
        if not f.filename.lower().endswith(".pdf"):
            return err("Only .pdf files are accepted.", 415)
        data = f.read()
        if not data.startswith(b"%PDF-"):
            return err("File content is not a valid PDF.", 415)
        if len(data) > config.MAX_UPLOAD_BYTES:
            return err("File too large.", 413)
        name = re.sub(r"[^\w.\- ]", "_", Path(f.filename).name)[:120]
        # The upload exists only for the duration of the request, then it is deleted.
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "upload.pdf"
            p.write_bytes(data)
            return run_audit(str(p), name, request.form.get("engine", "auto"))

    @app.get("/api/sample")
    def sample():
        if not config.SAMPLE_PDF.exists():
            return err("Sample contract is not installed.", 404)
        return run_audit(str(config.SAMPLE_PDF), "sample_contract.pdf", request.args.get("engine", "auto"))

    @app.get("/api/audits/<rid>")
    def get_audit(rid):
        r = load(rid)
        return jsonify(r) if r else err("Audit not found.", 404)

    @app.get("/api/audits/<rid>/report.md")
    def get_md(rid):
        r = load(rid)
        if not r:
            return err("Audit not found.", 404)
        return Response(to_markdown(r), mimetype="text/markdown",
                        headers={"Content-Disposition": f'attachment; filename="clauseguard-{rid[:8]}.md"'})

    return app


app = create_app()

if __name__ == "__main__":
    import os
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
