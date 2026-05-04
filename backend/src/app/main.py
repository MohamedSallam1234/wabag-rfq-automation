"""Main application entry point."""

from fastapi import FastAPI

from app.api.routes import users

app = FastAPI(title="WABAG RFQ Automation API", version="0.1.0")
app.include_router(users.router)


@app.get("/")
def read_root() -> dict[str, str]:
    """Root endpoint."""
    return {"status": "ok", "message": "Welcome to the WABAG RFQ Automation API"}


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
