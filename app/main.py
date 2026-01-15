from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from app.db import engine
from app.models import Base
from app.routes.api import router as api_router
from app.routes.home import router as home_router
from app.routes.industries import router as industries_router
from app.routes.stocks import router as stocks_router
from app.seed import seed_defaults
from app.services.scheduler import start_scheduler
from app.services.updater import update_all_prices


def create_app() -> FastAPI:
    app = FastAPI(title="Stock Performance Tracker")
    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Serve built React frontend (if available)
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend_dist.exists():

        @app.middleware("http")
        async def spa_fallback(request, call_next):
            # Let backend routes through
            if request.url.path.startswith(("/api", "/static", "/update-now", "/backfill-now")):
                return await call_next(request)
            # Try static file from frontend/dist
            try:
                file_path = frontend_dist / request.url.path.lstrip("/")
                if file_path.is_file():
                    return FileResponse(file_path)
            except Exception:
                pass
            # Fallback to index.html for SPA client routing
            index_file = frontend_dist / "index.html"
            if index_file.exists():
                return FileResponse(index_file, media_type="text/html")
            return await call_next(request)

    app.include_router(api_router)
    app.include_router(home_router)
    app.include_router(stocks_router)
    app.include_router(industries_router)

    @app.on_event("startup")
    def _startup() -> None:
        Base.metadata.create_all(bind=engine)

        from app.db import SessionLocal

        session = SessionLocal()
        try:
            seed_defaults(session)
            session.commit()
        finally:
            session.close()

        app.state.scheduler = start_scheduler()

        def _initial_update() -> None:
            import os
            # Skip auto-update on Render or when explicitly disabled to avoid rate limits
            if os.getenv("PORT") or os.getenv("DISABLE_STARTUP_UPDATE"):
                print("[startup] Skipping initial update (running on Render or DISABLE_STARTUP_UPDATE set)")
                return
            from app.db import SessionLocal

            s = SessionLocal()
            try:
                update_all_prices(s)
            finally:
                s.close()

        threading.Thread(target=_initial_update, daemon=True).start()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        sched = getattr(app.state, "scheduler", None)
        if sched is not None:
            sched.shutdown(wait=False)

    return app


app = create_app()
