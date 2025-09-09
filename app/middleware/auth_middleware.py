# app/middleware/auth_middleware.py
import os
import secrets
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html

# Security instance
security = HTTPBasic()

def get_docs_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Validate credentials for documentation access"""
    # Get credentials from environment variables
    correct_username = os.getenv("DOCS_USERNAME", "admin")
    correct_password = os.getenv("DOCS_PASSWORD", "dev123")
    
    # Use secrets.compare_digest for secure comparison
    username_ok = secrets.compare_digest(credentials.username, correct_username)
    password_ok = secrets.compare_digest(credentials.password, correct_password)
    
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

def setup_docs_protection(app: FastAPI):
    """Setup documentation protection based on environment"""
    
    # Check if we're in production and docs should be protected
    environment = os.getenv("ENVIRONMENT", "development")
    protect_docs = os.getenv("PROTECT_DOCS", "false").lower() in ("true", "1", "yes")
    
    if environment == "production" or protect_docs:
        # In production: protect docs with authentication
        @app.get("/docs", include_in_schema=False)
        async def get_swagger_documentation(username: str = Depends(get_docs_credentials)):
            return get_swagger_ui_html(
                openapi_url="/openapi.json", 
                title="Unitrust API - Documentation",
                swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
                swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"
            )

        @app.get("/redoc", include_in_schema=False)
        async def get_redoc_documentation(username: str = Depends(get_docs_credentials)):
            return get_redoc_html(
                openapi_url="/openapi.json", 
                title="Unitrust API - Documentation"
            )
        
        print("🔐 Documentation is PROTECTED with authentication")
        print(f"📝 Username: {os.getenv('DOCS_USERNAME', 'admin')}")
        print(f"🔑 Password: {os.getenv('DOCS_PASSWORD', 'dev123')}")
    else:
        # In development: docs are open (no authentication required)
        @app.get("/docs", include_in_schema=False)
        async def get_swagger_documentation():
            return get_swagger_ui_html(
                openapi_url="/openapi.json", 
                title="Unitrust API - Documentation",
                swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
                swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"
            )

        @app.get("/redoc", include_in_schema=False)
        async def get_redoc_documentation():
            return get_redoc_html(
                openapi_url="/openapi.json", 
                title="Unitrust API - Documentation"
            )
        
        print("🔓 Documentation is OPEN for development")
        print("📖 Access: http://localhost:8000/docs")
        print("📖 Access: http://localhost:8000/redoc")
