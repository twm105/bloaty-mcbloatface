from fastapi import FastAPI, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.exceptions import HTTPException

from app.api import routes, meals, symptoms, diagnosis, diagnosis_sse, auth

app = FastAPI(title="Bloaty McBloatface", version="0.1.0")

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
                status_code=status.HTTP_303_SEE_OTHER
            )

    # For all other cases, return the original error
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


# Include routers
app.include_router(auth.router)
app.include_router(routes.router)
app.include_router(meals.router)
app.include_router(symptoms.router)
app.include_router(diagnosis.router)
app.include_router(diagnosis_sse.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
