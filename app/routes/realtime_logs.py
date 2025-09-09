# app/routes/realtime_logs.py
import asyncio
import json
import time
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from ..utils.log_buffer import log_buffer, get_recent_logs, get_log_stats
from ..middleware.auth_middleware import get_docs_credentials

router = APIRouter(prefix="/logs", tags=["Real-time Logs"])

# Store active subscribers
active_subscribers = []

class LogSubscriber:
    """Handles real-time log streaming"""
    
    def __init__(self):
        self.queue = asyncio.Queue()
        self.active = True
        self.last_log_count = 0
    
    async def add_log(self, log_entry):
        """Add log entry to queue"""
        if self.active:
            await self.queue.put(log_entry)
    
    async def get_logs(self):
        """Get logs from queue"""
        while self.active:
            try:
                # Check for new logs in buffer
                current_logs = get_recent_logs(limit=100)
                if len(current_logs) > self.last_log_count:
                    # Send new logs
                    new_logs = current_logs[self.last_log_count:]
                    for log_entry in new_logs:
                        yield f"data: {json.dumps(log_entry)}\n\n"
                    self.last_log_count = len(current_logs)
                else:
                    # Send heartbeat
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()})}\n\n"
                
                # Wait before next check
                await asyncio.sleep(1.0)
                
            except Exception as e:
                print(f"Error in log streaming: {e}")
                break
    
    def stop(self):
        """Stop the subscriber"""
        self.active = False

@router.get("/stream")
async def stream_logs(username: str = Depends(get_docs_credentials)):
    """Stream logs in real-time using Server-Sent Events"""
    
    # Create new subscriber
    subscriber = LogSubscriber()
    active_subscribers.append(subscriber)
    
    try:
        # Stream logs
        return StreamingResponse(
            subscriber.get_logs(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Cache-Control",
            }
        )
    finally:
        # Clean up subscriber
        subscriber.stop()
        if subscriber in active_subscribers:
            active_subscribers.remove(subscriber)

@router.get("/recent")
async def get_recent_logs_endpoint(
    limit: int = 50,
    level: str = None,
    username: str = Depends(get_docs_credentials)
):
    """Get recent log entries"""
    return get_recent_logs(limit=limit, level=level)

@router.get("/stats")
async def get_log_stats_endpoint(username: str = Depends(get_docs_credentials)):
    """Get log statistics"""
    return get_log_stats()

@router.post("/clear")
async def clear_logs(username: str = Depends(get_docs_credentials)):
    """Clear all logs"""
    log_buffer.clear_logs()
    return {"message": "Logs cleared successfully"}
