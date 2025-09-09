# app/utils/performance_monitor.py
import time
import psutil
import threading
from contextlib import contextmanager
from typing import Dict, Any, Optional
from ..utils.logger import get_logger, log_performance

logger = get_logger("unitrust_api.performance")

class PerformanceMonitor:
    """Monitor system performance and resource usage"""
    
    def __init__(self):
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0
        self.total_response_time = 0.0
        self.lock = threading.Lock()
    
    def increment_request(self, response_time: float, is_error: bool = False):
        """Increment request counters"""
        with self.lock:
            self.request_count += 1
            self.total_response_time += response_time
            if is_error:
                self.error_count += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current performance statistics"""
        with self.lock:
            uptime = time.time() - self.start_time
            avg_response_time = (
                self.total_response_time / self.request_count 
                if self.request_count > 0 else 0
            )
            error_rate = (
                self.error_count / self.request_count 
                if self.request_count > 0 else 0
            )
            
            return {
                "uptime_seconds": uptime,
                "uptime_human": self._format_uptime(uptime),
                "total_requests": self.request_count,
                "error_count": self.error_count,
                "error_rate": error_rate,
                "avg_response_time": avg_response_time,
                "requests_per_minute": (self.request_count / uptime) * 60 if uptime > 0 else 0
            }
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get system resource statistics"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            
            # Disk usage
            disk = psutil.disk_usage('/')
            
            return {
                "cpu_percent": cpu_percent,
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "memory_used_gb": round(memory.used / (1024**3), 2),
                "memory_percent": memory.percent,
                "disk_total_gb": round(disk.total / (1024**3), 2),
                "disk_used_gb": round(disk.used / (1024**3), 2),
                "disk_percent": round((disk.used / disk.total) * 100, 2)
            }
        except Exception as e:
            logger.error(f"Failed to get system stats: {e}")
            return {}
    
    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human readable format"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}m"
        elif seconds < 86400:
            return f"{seconds/3600:.1f}h"
        else:
            return f"{seconds/86400:.1f}d"
    
    def log_performance_summary(self):
        """Log current performance summary"""
        stats = self.get_stats()
        system_stats = self.get_system_stats()
        
        logger.info(
            f"Performance Summary | Uptime: {stats['uptime_human']} | "
            f"Requests: {stats['total_requests']} | "
            f"Avg Response: {stats['avg_response_time']:.3f}s | "
            f"Error Rate: {stats['error_rate']:.2%} | "
            f"CPU: {system_stats.get('cpu_percent', 0):.1f}% | "
            f"Memory: {system_stats.get('memory_percent', 0):.1f}%"
        )

# Global performance monitor instance
performance_monitor = PerformanceMonitor()

@contextmanager
def monitor_operation(operation_name: str):
    """Context manager to monitor operation performance"""
    start_time = time.time()
    start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
    
    try:
        yield
        success = True
    except Exception as e:
        success = False
        raise
    finally:
        duration = time.time() - start_time
        end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        memory_delta = end_memory - start_memory
        
        # Log performance
        log_performance(
            logger,
            operation=operation_name,
            duration=duration,
            memory_usage=memory_delta
        )
        
        # Update monitor
        performance_monitor.increment_request(duration, not success)

def log_system_health():
    """Log current system health status"""
    stats = performance_monitor.get_stats()
    system_stats = performance_monitor.get_system_stats()
    
    # Check for warnings
    warnings = []
    
    if system_stats.get('cpu_percent', 0) > 80:
        warnings.append(f"High CPU usage: {system_stats['cpu_percent']:.1f}%")
    
    if system_stats.get('memory_percent', 0) > 85:
        warnings.append(f"High memory usage: {system_stats['memory_percent']:.1f}%")
    
    if stats['error_rate'] > 0.1:  # 10% error rate
        warnings.append(f"High error rate: {stats['error_rate']:.2%}")
    
    if stats['avg_response_time'] > 2.0:  # 2 seconds
        warnings.append(f"Slow response time: {stats['avg_response_time']:.3f}s")
    
    if warnings:
        logger.warning(f"System Health Warnings: {'; '.join(warnings)}")
    else:
        logger.info("System Health: OK")

# Background task to log performance periodically
def start_performance_monitoring(interval: int = 300):  # 5 minutes
    """Start background performance monitoring"""
    def monitor_loop():
        while True:
            try:
                log_system_health()
                performance_monitor.log_performance_summary()
                time.sleep(interval)
            except Exception as e:
                logger.error(f"Performance monitoring error: {e}")
                time.sleep(60)  # Wait 1 minute before retrying
    
    thread = threading.Thread(target=monitor_loop, daemon=True)
    thread.start()
    logger.info(f"Performance monitoring started (interval: {interval}s)")
    return thread
