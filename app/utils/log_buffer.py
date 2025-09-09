# app/utils/log_buffer.py
import threading
import time
from collections import deque
from typing import List, Dict, Any, Optional
from datetime import datetime

class LogBuffer:
    """Thread-safe circular buffer for storing log entries"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.buffer = deque(maxlen=max_size)
        self.lock = threading.Lock()
        self.subscribers = []
        self.subscriber_lock = threading.Lock()
    
    def add_log(self, level: str, module: str, message: str, timestamp: Optional[str] = None):
        """Add a log entry to the buffer"""
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "module": module,
            "message": message
        }
        
        with self.lock:
            self.buffer.append(log_entry)
        
        # Notify subscribers
        self._notify_subscribers(log_entry)
    
    def get_recent_logs(self, limit: int = 50, level: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent log entries"""
        with self.lock:
            logs = list(self.buffer)
        
        # Filter by level if specified
        if level:
            logs = [log for log in logs if log["level"].lower() == level.lower()]
        
        # Return most recent logs
        return logs[-limit:] if logs else []
    
    def get_all_logs(self) -> List[Dict[str, Any]]:
        """Get all log entries"""
        with self.lock:
            return list(self.buffer)
    
    def clear_logs(self):
        """Clear all log entries"""
        with self.lock:
            self.buffer.clear()
    
    def subscribe(self, callback):
        """Subscribe to new log entries"""
        with self.subscriber_lock:
            self.subscribers.append(callback)
    
    def unsubscribe(self, callback):
        """Unsubscribe from log entries"""
        with self.subscriber_lock:
            if callback in self.subscribers:
                self.subscribers.remove(callback)
    
    def _notify_subscribers(self, log_entry: Dict[str, Any]):
        """Notify all subscribers of new log entry"""
        with self.subscriber_lock:
            for callback in self.subscribers:
                try:
                    callback(log_entry)
                except Exception as e:
                    print(f"Error notifying subscriber: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get log statistics"""
        with self.lock:
            total_logs = len(self.buffer)
            level_counts = {}
            
            for log in self.buffer:
                level = log["level"]
                level_counts[level] = level_counts.get(level, 0) + 1
            
            return {
                "total_logs": total_logs,
                "level_counts": level_counts,
                "buffer_size": self.max_size,
                "buffer_usage": (total_logs / self.max_size) * 100
            }

# Global log buffer instance
log_buffer = LogBuffer(max_size=1000)

def add_log_to_buffer(level: str, module: str, message: str):
    """Add a log entry to the global buffer"""
    log_buffer.add_log(level, module, message)

def get_recent_logs(limit: int = 50, level: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get recent logs from the global buffer"""
    return log_buffer.get_recent_logs(limit, level)

def get_log_stats() -> Dict[str, Any]:
    """Get log statistics from the global buffer"""
    return log_buffer.get_stats()
