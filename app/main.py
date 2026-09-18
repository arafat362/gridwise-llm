from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app import __version__
from app.api.routes import router

app = FastAPI(
    title="GridWise LLM",
    description="BUP CSE Fest 2026 energy optimization API",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=".*",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS", "PUT", "PATCH", "DELETE", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

app.include_router(router)


@app.exception_handler(RequestValidationError)
async def bad_request(_request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": exc.errors()})


@app.exception_handler(ValidationError)
async def pydantic_bad_request(_request: Request, exc: ValidationError):
    return JSONResponse(status_code=400, content={"detail": exc.errors()})
