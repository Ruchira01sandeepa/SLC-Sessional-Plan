from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .routers import admin, auth, calendar, development, fitness, meta, plan_versions, players, plans, screening, squads, testing, workload

app = FastAPI(title="Sri Lanka Cricket Junior (U15 / U17) Player Workload, Development & Seasonal Planning System",
              version="0.1.0")
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(players.router)
app.include_router(meta.router)
app.include_router(squads.router)
app.include_router(screening.router)
app.include_router(calendar.router)
app.include_router(fitness.router)
app.include_router(plans.router)
app.include_router(workload.router)
app.include_router(testing.router)
app.include_router(development.router)
app.include_router(plan_versions.router)


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/ui"):
        # The UI has no inline scripts or styles, so a strict policy is possible: injected script would not run.
        resp.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                                                   "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        resp.headers["Cache-Control"] = "no-cache"
    elif not request.url.path.startswith(("/docs", "/openapi", "/redoc")):
        resp.headers["Cache-Control"] = "no-store"        # API data (incl. medical) must not sit in browser/proxy caches
    return resp


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/ui/")


app.mount("/ui", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="ui")
