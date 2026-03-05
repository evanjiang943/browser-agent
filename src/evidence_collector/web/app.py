"""FastAPI application: file upload, WebSocket, static serving."""

from __future__ import annotations

import tempfile
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, UploadFile, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from evidence_collector.web.session import SessionManager
from evidence_collector.web.ws_handler import handle_websocket

app = FastAPI(title="Evidence Collector")

_sessions = SessionManager()
_upload_dir = Path(tempfile.mkdtemp(prefix="evidence_uploads_"))
_output_base = Path(tempfile.mkdtemp(prefix="evidence_output_"))

# Static files (index.html)
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(_static_dir / "index.html"))


@app.post("/api/upload")
async def upload_file(file: UploadFile) -> JSONResponse:
    """Accept a file upload, save to temp dir, return file_id."""
    suffix = Path(file.filename or "upload").suffix
    file_id = f"{uuid.uuid4().hex[:12]}{suffix}"
    dest = _upload_dir / file_id
    content = await file.read()
    dest.write_bytes(content)
    return JSONResponse({
        "file_id": file_id,
        "filename": file.filename,
    })


@app.websocket("/api/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    await handle_websocket(ws, _sessions, _upload_dir, _output_base)


@app.get("/api/files/{session_id}/{path:path}")
async def serve_file(session_id: str, path: str) -> FileResponse:
    """Serve output files for download."""
    file_path = _output_base / session_id / path
    if not file_path.exists() or not file_path.is_file():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(str(file_path), filename=file_path.name)


@app.get("/api/download/{session_id}")
async def download_zip(session_id: str) -> Response:
    """Create and serve a zip archive of all output files."""
    out_dir = _output_base / session_id
    if not out_dir.exists() or not out_dir.is_dir():
        return JSONResponse({"error": "Session not found"}, status_code=404)

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(out_dir.rglob("*")):
            if p.is_file() and not p.name.startswith("."):
                arcname = str(p.relative_to(out_dir))
                zf.write(p, arcname)
    buf.seek(0)
    content = buf.getvalue()

    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="evidence-results.zip"',
            "Content-Length": str(len(content)),
        },
    )


def main() -> None:
    """Entry point for `evidence-web` command."""
    import uvicorn

    uvicorn.run(
        "evidence_collector.web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
