from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.api import analyzer_router, plan_router

app = FastAPI(
    title="LangGraph Learning Plan Demo",
    description="A demo service for generating structured learning plans.",
    version="0.1.0",
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.include_router(analyzer_router)
app.include_router(plan_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "LangGraph Learning Plan Demo",
        "analyzer_demo": "/analyzer-demo",
        "generate_plan": "/api/v1/plan/generate",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/analyzer-demo", response_class=HTMLResponse)
def analyzer_demo() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "analyzer_demo.html").read_text(encoding="utf-8"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import os
    import socket

    import uvicorn

    os.chdir(PROJECT_ROOT)

    def find_available_port(start_port: int) -> int:
        for candidate in range(start_port, start_port + 50):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                try:
                    sock.bind(("127.0.0.1", candidate))
                except OSError:
                    continue
                return candidate
        raise RuntimeError(f"No available port found from {start_port} to {start_port + 49}")

    port = find_available_port(int(os.getenv("APP_PORT", "18010")))
    print(f"Analyzer demo: http://127.0.0.1:{port}/analyzer-demo")
    uvicorn.run(app, host="127.0.0.1", port=port, reload=False)
