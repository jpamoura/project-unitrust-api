# app/main.py
import os
from fastapi import FastAPI
from .routes import underwriting_routes, returns_routes, csv_routes, logs_routes, realtime_logs
from .middleware.auth_middleware import setup_docs_protection
from .middleware.logging_middleware import LoggingMiddleware, SecurityLoggingMiddleware
from .utils.logger import get_logger, setup_logger
from .utils.performance_monitor import start_performance_monitoring

# Setup logging
logger = setup_logger(
    name="unitrust_api",
    level=os.getenv("LOG_LEVEL", "INFO"),
    log_file=os.getenv("LOG_FILE", "logs/unitrust_api.log"),
    enable_console=True,
    enable_colors=True
)

# Create FastAPI app
app = FastAPI(
    title="Unitrust API - Underwriting & Returns Extractor",
    description="A robust, modular FastAPI application for extracting data from PDF underwriting and returns reports with advanced CSV comparison capabilities.",
    version="2.0.0",
    docs_url=None,  # Will be set by middleware
    redoc_url=None  # Will be set by middleware
)

# Add middleware
app.add_middleware(SecurityLoggingMiddleware)
app.add_middleware(LoggingMiddleware)

# Include routers
app.include_router(underwriting_routes.router)
app.include_router(returns_routes.router)
app.include_router(csv_routes.router)
app.include_router(logs_routes.router)
app.include_router(realtime_logs.router)

# Setup documentation protection based on environment
setup_docs_protection(app)

# Start performance monitoring
start_performance_monitoring(interval=300)  # 5 minutes

logger.info("🚀 Unitrust API started successfully")

@app.get("/")
def root():
    environment = os.getenv("ENVIRONMENT", "development")
    return {
        "ok": True, 
        "service": "Unitrust API - Underwriting & Returns Extractor",
        "version": "2.0.0",
        "environment": environment,
        "docs_protected": os.getenv("PROTECT_DOCS", "false").lower() in ("true", "1", "yes")
    }

@app.get("/healthz")
def healthz():
    return {"ok": True, "status": "healthy"}
