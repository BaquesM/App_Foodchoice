import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from backend.app.db.init_db import init_db
from backend.app.api.routes import router as api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database on startup
    init_db()
    yield

# Create the FastAPI application instance
app = FastAPI(
    title="FoodChoice API",
    description="Smart recipe recommendation and ingredient substitution API",
    version="0.1.0",
    lifespan=lifespan,
)

# Register the API router
app.include_router(api_router)

# CORS configuration (allows browsers to communicate securely with the API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/api/health", tags=["System"])
def health_check():
    """Check if the API is online and functional."""
    return {
        "status": "healthy",
        "service": "FoodChoice Backend",
        "version": "0.1.0"
    }

# Path to static frontend files
frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"

if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/", include_in_schema=False)
    def serve_frontend():
        index_file = frontend_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "Welcome to FoodChoice API. Visit /docs to test the API."}
