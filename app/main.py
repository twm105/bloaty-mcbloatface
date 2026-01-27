from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from app.api import routes, meals, symptoms

app = FastAPI(title="Bloaty McBloatface", version="0.1.0")

# Mount static files and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
templates = Jinja2Templates(directory="app/templates")

# Include routers
app.include_router(routes.router)
app.include_router(meals.router)
app.include_router(symptoms.router)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
