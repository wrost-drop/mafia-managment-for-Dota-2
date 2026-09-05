from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import router
from database import initialize_database

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Dota Mafia Manager")
app.include_router(router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.on_event("startup")
async def startup() -> None:
    await initialize_database()
