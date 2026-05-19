from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse


def register_web_routes(app: FastAPI, *, web_dist_dir: str = "web/dist") -> None:
    dist = Path(web_dist_dir)
    index = dist / "index.html"

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/app", status_code=307)

    if not index.exists():

        @app.get("/app", include_in_schema=False)
        @app.get("/app/{path:path}", include_in_schema=False)
        async def web_not_built() -> HTMLResponse:
            return HTMLResponse(
                """
                <!doctype html>
                <html lang="en">
                  <head>
                    <meta charset="utf-8" />
                    <meta name="viewport" content="width=device-width, initial-scale=1" />
                    <title>SQL Assistant</title>
                    <style>
                      body {
                        margin: 0;
                        min-height: 100vh;
                        display: grid;
                        place-items: center;
                        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
                          sans-serif;
                        background: #f5f5f7;
                        color: #1d1d1f;
                      }
                      .card {
                        width: min(680px, calc(100vw - 32px));
                        padding: 32px;
                        border-radius: 24px;
                        background: rgba(255, 255, 255, 0.82);
                      }
                      code {
                        display: block;
                        padding: 12px 14px;
                        border-radius: 12px;
                        background: #1c1c1e;
                        color: #f5f5f7;
                        margin-top: 10px;
                        font-size: 14px;
                      }
                    </style>
                  </head>
                  <body>
                    <main class="card">
                      <h1>SQL Assistant Web App</h1>
                      <p>The web app is not built yet.</p>
                      <code>cd web</code>
                      <code>npm install</code>
                      <code>npm run dev</code>
                      <code>npm run build</code>
                    </main>
                  </body>
                </html>
                """,
            )

        return

    dist_resolved = dist.resolve()

    def _safe_file(path: Path) -> Path | None:
        try:
            resolved = path.resolve()
        except OSError:
            return None
        if dist_resolved == resolved or dist_resolved in resolved.parents:
            return resolved
        return None

    @app.get("/app", include_in_schema=False)
    async def spa_index() -> FileResponse:
        return FileResponse(index)

    @app.get("/app/{resource_path:path}", include_in_schema=False)
    async def spa_assets(resource_path: str) -> FileResponse:
        candidate = _safe_file(dist / resource_path)
        if candidate is not None and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)
