from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import answers
from app.api.v1 import chat
from app.api.v1 import user
from app.exceptions.base import AppException


app = FastAPI(
    title = "ELEGANTBot",
    description= "ElegantBot API",
    version="0.0.1"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins= ["http://localhost:3000"],
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"],
)

app.include_router(user.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(answers.router, prefix="/api/v1")

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.get("/")
def root():
    return {"message": "ElegantBot Chat API"}