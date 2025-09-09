# app/utils/logger.py
import logging
import sys
import os
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels"""
    
    # Color codes
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }
    
    def format(self, record):
        # Add color to the level name
        if record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{self.COLORS['RESET']}"
        
        # Format the message
        return super().format(record)

def setup_logger(
    name: str = "unitrust_api",
    level: str = "INFO",
    log_file: Optional[str] = None,
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    enable_console: bool = True,
    enable_colors: bool = True
) -> logging.Logger:
    """
    Setup a comprehensive logger for the application
    
    Args:
        name: Logger name
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        max_file_size: Maximum log file size in bytes
        backup_count: Number of backup files to keep
        enable_console: Enable console logging
        enable_colors: Enable colored console output
    """
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create formatters
    if enable_colors:
        console_formatter = ColoredFormatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(getattr(logging, level.upper()))
        logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        # Create logs directory if it doesn't exist
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Rotating file handler
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)  # File always logs everything
        logger.addHandler(file_handler)
    
    return logger

def log_request(logger: logging.Logger, method: str, url: str, status_code: int, 
                response_time: float, user_agent: str = None, ip: str = None):
    """Log HTTP request details"""
    logger.info(
        f"HTTP {method} {url} | Status: {status_code} | "
        f"Response Time: {response_time:.3f}s | IP: {ip or 'unknown'} | "
        f"User-Agent: {user_agent or 'unknown'}"
    )

def log_file_upload(logger: logging.Logger, filename: str, file_size: int, 
                   file_type: str, success: bool, error: str = None):
    """Log file upload events"""
    if success:
        logger.info(
            f"File Upload Success | Name: {filename} | Size: {file_size} bytes | "
            f"Type: {file_type}"
        )
    else:
        logger.error(
            f"File Upload Failed | Name: {filename} | Size: {file_size} bytes | "
            f"Type: {file_type} | Error: {error}"
        )

def log_parsing(logger: logging.Logger, parser_type: str, items_count: int, 
               processing_time: float, success: bool, error: str = None):
    """Log parsing operations"""
    if success:
        logger.info(
            f"Parsing Success | Type: {parser_type} | Items: {items_count} | "
            f"Time: {processing_time:.3f}s"
        )
    else:
        logger.error(
            f"Parsing Failed | Type: {parser_type} | Time: {processing_time:.3f}s | "
            f"Error: {error}"
        )

def log_api_call(logger: logging.Logger, endpoint: str, method: str, 
                status_code: int, response_time: float, payload_size: int = None):
    """Log external API calls"""
    logger.info(
        f"API Call | {method} {endpoint} | Status: {status_code} | "
        f"Time: {response_time:.3f}s | Payload: {payload_size or 'unknown'} bytes"
    )

def log_security_event(logger: logging.Logger, event_type: str, details: str, 
                      ip: str = None, user: str = None):
    """Log security-related events"""
    logger.warning(
        f"Security Event | Type: {event_type} | Details: {details} | "
        f"IP: {ip or 'unknown'} | User: {user or 'unknown'}"
    )

def log_performance(logger: logging.Logger, operation: str, duration: float, 
                   memory_usage: float = None, cpu_usage: float = None):
    """Log performance metrics"""
    logger.info(
        f"Performance | Operation: {operation} | Duration: {duration:.3f}s | "
        f"Memory: {memory_usage or 'unknown'} MB | CPU: {cpu_usage or 'unknown'}%"
    )

# Global logger instance
def get_logger(name: str = "unitrust_api") -> logging.Logger:
    """Get the global logger instance"""
    return logging.getLogger(name)

# Custom log handler to add logs to buffer
class BufferLogHandler(logging.Handler):
    """Custom handler to add logs to the buffer"""
    
    def __init__(self, buffer):
        super().__init__()
        self.buffer = buffer
    
    def emit(self, record):
        try:
            # Format the log message
            message = self.format(record)
            
            # Add to buffer
            self.buffer.add_log(
                level=record.levelname,
                module=record.name,
                message=message,
                timestamp=datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
            )
        except Exception:
            pass  # Ignore errors in logging

# Initialize default logger
default_logger = setup_logger(
    name="unitrust_api",
    level=os.getenv("LOG_LEVEL", "INFO"),
    log_file=os.getenv("LOG_FILE", "logs/unitrust_api.log"),
    enable_console=True,
    enable_colors=True
)

# Add buffer handler to all loggers
from .log_buffer import log_buffer
buffer_handler = BufferLogHandler(log_buffer)
buffer_handler.setLevel(logging.DEBUG)
default_logger.addHandler(buffer_handler)
