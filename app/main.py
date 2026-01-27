from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from app.api import routes

app = FastAPI(title="Bloaty McBloatface", version="0.1.0")

# Mount static files and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Include routers
app.include_router(routes.router)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
