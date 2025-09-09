# app/middleware/logging_middleware.py
import time
import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from ..utils.logger import get_logger, log_request, log_security_event

logger = get_logger("unitrust_api.middleware")

class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests and responses"""
    
    async def dispatch(self, request: Request, call_next):
        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]
        
        # Start timing
        start_time = time.time()
        
        # Get client info
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Log request start
        logger.info(
            f"Request Started | ID: {request_id} | {request.method} {request.url.path} | "
            f"IP: {client_ip} | User-Agent: {user_agent[:50]}..."
        )
        
        # Add request ID to headers for tracing
        request.state.request_id = request_id
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate response time
            response_time = time.time() - start_time
            
            # Log successful request
            log_request(
                logger,
                method=request.method,
                url=str(request.url),
                status_code=response.status_code,
                response_time=response_time,
                user_agent=user_agent,
                ip=client_ip
            )
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{response_time:.3f}s"
            
            # Log slow requests
            if response_time > 5.0:
                logger.warning(
                    f"Slow Request | ID: {request_id} | {request.method} {request.url.path} | "
                    f"Time: {response_time:.3f}s | Threshold: 5.0s"
                )
            
            return response
            
        except Exception as e:
            # Calculate response time for failed requests
            response_time = time.time() - start_time
            
            # Log error
            logger.error(
                f"Request Failed | ID: {request_id} | {request.method} {request.url.path} | "
                f"Error: {str(e)} | Time: {response_time:.3f}s | IP: {client_ip}"
            )
            
            # Log security event for suspicious requests
            if response_time < 0.1:  # Very fast requests might be attacks
                log_security_event(
                    logger,
                    event_type="suspicious_request",
                    details=f"Very fast request: {response_time:.3f}s",
                    ip=client_ip
                )
            
            raise

class SecurityLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log security-related events"""
    
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        
        # Check for suspicious patterns
        suspicious_patterns = [
            "admin", "login", "password", "token", "auth",
            "sql", "script", "eval", "exec", "cmd"
        ]
        
        # Check URL path
        path_lower = request.url.path.lower()
        for pattern in suspicious_patterns:
            if pattern in path_lower:
                log_security_event(
                    logger,
                    event_type="suspicious_path",
                    details=f"Path contains '{pattern}': {request.url.path}",
                    ip=client_ip
                )
        
        # Check for missing or suspicious headers
        if not request.headers.get("user-agent"):
            log_security_event(
                logger,
                event_type="missing_user_agent",
                details="Request without User-Agent header",
                ip=client_ip
            )
        
        # Check for suspicious user agents
        user_agent = request.headers.get("user-agent", "").lower()
        if any(bot in user_agent for bot in ["bot", "crawler", "spider", "scraper"]):
            log_security_event(
                logger,
                event_type="bot_detected",
                details=f"Bot User-Agent: {user_agent}",
                ip=client_ip
            )
        
        return await call_next(request)
