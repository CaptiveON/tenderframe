from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import answers
from app.api.v1 import chat
from app.api.v1 import user
from app.core.config import settings
from app.exceptions.base import AppException


app = FastAPI(
    title = "TenderFrame API",
    description= "Auditable UK VAT guidance with verifiable citations.",
    version="1.0.0"
)

# F9: CORS origins from env (comma-separated), not "*"; methods/headers scoped.
_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins= _origins,
    allow_credentials = True,
    allow_methods = ["GET", "POST", "OPTIONS"],
    allow_headers = ["Authorization", "Content-Type"],
)


# F8: baseline security response headers on every response.
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response

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
    return {"message": "TenderFrame API"}