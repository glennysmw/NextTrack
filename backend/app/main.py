"""FastAPI application entrypoint: CORS, lifespan startup, and routing."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import settings
from app.data import musicbrainz
from app.engine.recommender import RecommendationError

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("nexttrack")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Configure MusicBrainz at startup.

    Playback is resolved via YouTube Music's internal API (``ytmusicapi``), which
    needs no API key and has no per-day quota — so there is nothing to validate
    here any more. The legacy ``YOUTUBE_API_KEY`` is no longer read.
    """
    musicbrainz.configure()

    # ASCII-only banner: a non-ASCII glyph here raises UnicodeEncodeError under any
    # non-UTF-8 stdout (file redirect, Docker logs, Windows service), crashing startup.
    logger.info(
        "%s v%s ready -- stateless music recommendations. Docs: http://localhost:8000/docs",
        settings.APP_NAME,
        settings.VERSION,
    )
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description=(
        "Privacy-first, stateless music recommendation API. The server stores no "
        "user data between requests — every call carries its own listening history."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RecommendationError)
async def recommendation_error_handler(
    _request: Request, exc: RecommendationError
) -> JSONResponse:
    """Surface a failed recommendation as {detail, reason}.

    `detail` stays a human-readable string (unchanged contract); `reason` is the
    machine-readable code the frontend maps to specific guidance.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "reason": exc.reason},
    )


app.include_router(router)


@app.get("/", tags=["meta"])
async def root() -> dict:
    """Minimal landing payload pointing at the interactive docs."""
    return {"name": settings.APP_NAME, "version": settings.VERSION, "docs": "/docs"}
