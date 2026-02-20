import logging
from urllib.parse import urlparse

from fastapi import FastAPI, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import routes, meals, symptoms, diagnosis, diagnosis_sse, auth, feedback

logger = logging.getLogger(__name__)

app = FastAPI(title="Bloaty McBloatface", version="0.1.0")


# =============================================================================
# CSRF Origin Validation Middleware
# =============================================================================


class CSRFOriginMiddleware(BaseHTTPMiddleware):
    """
    Validate Origin/Referer headers on state-changing requests to prevent CSRF.

    - POST, PUT, PATCH, DELETE must include a matching Origin or Referer header
    - GET, HEAD, OPTIONS are always allowed (safe methods)
    - Health check endpoints are exempt
    """

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
    EXEMPT_PATHS = {"/health", "/nginx-health"}

    async def dispatch(self, request: Request, call_next):
        if request.method in self.SAFE_METHODS:
            return await call_next(request)

        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Determine the expected host from the request
        expected_host = request.headers.get("host", "")

        # Check Origin header first
        origin = request.headers.get("origin")
        if origin:
            parsed = urlparse(origin)
            origin_host = parsed.netloc
            if origin_host != expected_host:
                logger.warning(
                    "CSRF origin mismatch: origin=%s, expected=%s, path=%s",
                    origin,
                    expected_host,
                    request.url.path,
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Origin validation failed"},
                )
            return await call_next(request)

        # Fall back to Referer header
        referer = request.headers.get("referer")
        if referer:
            parsed = urlparse(referer)
            referer_host = parsed.netloc
            if referer_host != expected_host:
                logger.warning(
                    "CSRF referer mismatch: referer=%s, expected=%s, path=%s",
                    referer,
                    expected_host,
                    request.url.path,
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Origin validation failed"},
                )
            return await call_next(request)

        # No Origin or Referer — reject the request
        logger.warning(
            "CSRF missing origin/referer: method=%s, path=%s",
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=403,
            content={"detail": "Origin validation failed"},
        )


app.add_middleware(CSRFOriginMiddleware)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
templates = Jinja2Templates(directory="app/templates")


@app.exception_handler(HTTPException)
async def auth_exception_handler(request: Request, exc: HTTPException):
    """
    Redirect to login page for 401 errors on non-API requests.
    API requests (expecting JSON) still get the JSON error response.
    """
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        # Check if this is a browser request (not API/AJAX)
        accept = request.headers.get("accept", "")
        is_html_request = "text/html" in accept

        # Don't redirect API calls or htmx requests
        is_htmx = request.headers.get("hx-request") == "true"

        if is_html_request and not is_htmx:
            # Build return URL
            return_url = str(request.url.path)
            if request.url.query:
                return_url += f"?{request.url.query}"
            return RedirectResponse(
                url=f"/auth/login?next={return_url}",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    # For all other cases, return the original error
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# Include routers
app.include_router(auth.router)
app.include_router(routes.router)
app.include_router(meals.router)
app.include_router(symptoms.router)
app.include_router(diagnosis.router)
app.include_router(diagnosis_sse.router)
app.include_router(feedback.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
