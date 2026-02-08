from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.db import init_db
from app.routers.recommend import router as recommend_router
from app.routers.sync import router as sync_router

app = FastAPI(title="WatchWhat Web", version="0.1.0")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


app.include_router(sync_router, prefix="/api")
app.include_router(recommend_router, prefix="/api")
