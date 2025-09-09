# app/routes/logs_routes.py
import os
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional, List
from ..utils.logger import get_logger
from ..utils.performance_monitor import performance_monitor, log_system_health
from ..middleware.auth_middleware import get_docs_credentials
from fastapi.security import HTTPBasicCredentials

router = APIRouter(prefix="/logs", tags=["Logs & Monitoring"])
logger = get_logger("unitrust_api.logs")

@router.get("/", response_class=HTMLResponse)
async def logs_dashboard(username: str = Depends(get_docs_credentials)):
    """Logs dashboard with real-time monitoring"""
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Unitrust API - Logs Dashboard</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: 'Courier New', monospace; margin: 0; padding: 20px; background: #1e1e1e; color: #fff; }
            .header { background: #2d2d2d; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }
            .stat-card { background: #3d3d3d; padding: 15px; border-radius: 8px; text-align: center; }
            .stat-value { font-size: 24px; font-weight: bold; color: #4CAF50; }
            .stat-label { font-size: 12px; color: #aaa; margin-top: 5px; }
            .log-container { background: #2d2d2d; padding: 20px; border-radius: 8px; height: 400px; overflow-y: auto; }
            .log-entry { margin-bottom: 8px; padding: 5px; border-left: 3px solid #4CAF50; }
            .log-error { border-left-color: #f44336; }
            .log-warning { border-left-color: #ff9800; }
            .log-debug { border-left-color: #2196F3; }
            .controls { margin-bottom: 20px; }
            .btn { background: #4CAF50; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin-right: 10px; }
            .btn:hover { background: #45a049; }
            .btn-danger { background: #f44336; }
            .btn-danger:hover { background: #da190b; }
            .refresh-info { color: #aaa; font-size: 12px; margin-top: 10px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔍 Unitrust API - Logs Dashboard</h1>
            <p>Real-time monitoring and log visualization</p>
        </div>
        
        <div class="stats" id="stats">
            <div class="stat-card">
                <div class="stat-value" id="uptime">-</div>
                <div class="stat-label">Uptime</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="requests">-</div>
                <div class="stat-label">Total Requests</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="errors">-</div>
                <div class="stat-label">Errors</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="avg-response">-</div>
                <div class="stat-label">Avg Response (s)</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="cpu">-</div>
                <div class="stat-label">CPU %</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="memory">-</div>
                <div class="stat-label">Memory %</div>
            </div>
        </div>
        
        <div class="controls">
            <button class="btn" onclick="refreshLogs()">🔄 Refresh Logs</button>
            <button class="btn" onclick="clearLogs()">🗑️ Clear Logs</button>
            <button class="btn" onclick="testLogs()">🧪 Test Logs</button>
            <button class="btn btn-danger" onclick="downloadLogs()">📥 Download Logs</button>
            <span id="connectionStatus" style="margin-left: 20px; font-weight: bold;">🟡 Connecting...</span>
            <div class="refresh-info">Real-time logs streaming</div>
        </div>
        
        <div class="log-container" id="logContainer">
            <div class="log-entry">Loading logs...</div>
        </div>
        
        <script>
            let autoRefresh = true;
            let eventSource = null;
            let logCount = 0;
            
            // Real-time log streaming using polling
            let lastLogCount = 0;
            
            function startLogStream() {
                // Update connection status
                const status = document.getElementById('connectionStatus');
                if (status) {
                    status.textContent = '🟢 Connected (Polling)';
                    status.style.color = '#4CAF50';
                }
                
                // Start polling for new logs
                pollForLogs();
            }
            
            async function pollForLogs() {
                if (!autoRefresh) return;
                
                try {
                    const response = await fetch('/logs/recent?limit=100');
                    const logs = await response.json();
                    
                    if (logs.length > lastLogCount) {
                        // New logs available
                        const newLogs = logs.slice(lastLogCount);
                        newLogs.forEach(log => {
                            addLogToContainer(log);
                            logCount++;
                        });
                        lastLogCount = logs.length;
                        
                        // Update log count in header
                        document.title = `Logs Dashboard (${logCount} logs)`;
                    }
                    
                    // Update connection status
                    const status = document.getElementById('connectionStatus');
                    if (status) {
                        status.textContent = '🟢 Connected (Polling)';
                        status.style.color = '#4CAF50';
                    }
                    
                } catch (error) {
                    console.error('Error polling logs:', error);
                    const status = document.getElementById('connectionStatus');
                    if (status) {
                        status.textContent = '🔴 Disconnected';
                        status.style.color = '#f44336';
                    }
                }
                
                // Continue polling every 2 seconds
                setTimeout(pollForLogs, 2000);
            }
            
            function addLogToContainer(log) {
                const container = document.getElementById('logContainer');
                const div = document.createElement('div');
                div.className = `log-entry log-${log.level.toLowerCase()}`;
                div.innerHTML = `
                    <strong>[${log.timestamp}]</strong> 
                    <span style="color: #4CAF50;">[${log.level}]</span> 
                    <span style="color: #2196F3;">[${log.module}]</span> 
                    ${log.message}
                `;
                
                // Add to top of container
                container.insertBefore(div, container.firstChild);
                
                // Keep only last 100 logs visible
                while (container.children.length > 100) {
                    container.removeChild(container.lastChild);
                }
                
                // Auto-scroll to top for new logs
                container.scrollTop = 0;
            }
            
            async function fetchStats() {
                try {
                    const response = await fetch('/logs/stats');
                    const data = await response.json();
                    
                    document.getElementById('uptime').textContent = data.uptime_human || '-';
                    document.getElementById('requests').textContent = data.total_requests || '0';
                    document.getElementById('errors').textContent = data.error_count || '0';
                    document.getElementById('avg-response').textContent = (data.avg_response_time || 0).toFixed(3);
                    document.getElementById('cpu').textContent = (data.cpu_percent || 0).toFixed(1) + '%';
                    document.getElementById('memory').textContent = (data.memory_percent || 0).toFixed(1) + '%';
                } catch (error) {
                    console.error('Error fetching stats:', error);
                }
            }
            
            async function fetchLogs() {
                try {
                    const response = await fetch('/logs/recent');
                    const logs = await response.json();
                    
                    const container = document.getElementById('logContainer');
                    container.innerHTML = '';
                    logCount = 0;
                    
                    logs.forEach(log => {
                        addLogToContainer(log);
                        logCount++;
                    });
                    
                    document.title = `Logs Dashboard (${logCount} logs)`;
                    
                } catch (error) {
                    console.error('Error fetching logs:', error);
                }
            }
            
            function refreshLogs() {
                fetchStats();
                // Don't fetch logs here since we're using real-time streaming
            }
            
            async function clearLogs() {
                try {
                    await fetch('/logs/clear', { method: 'POST' });
                    document.getElementById('logContainer').innerHTML = '<div class="log-entry">Logs cleared</div>';
                    logCount = 0;
                    document.title = 'Logs Dashboard';
                } catch (error) {
                    console.error('Error clearing logs:', error);
                }
            }
            
            function downloadLogs() {
                window.open('/logs/download', '_blank');
            }
            
            async function testLogs() {
                try {
                    const response = await fetch('/logs/test', { method: 'POST' });
                    const data = await response.json();
                    console.log('Test logs generated:', data.message);
                } catch (error) {
                    console.error('Error generating test logs:', error);
                }
            }
            
            function toggleAutoRefresh() {
                autoRefresh = !autoRefresh;
                const button = document.querySelector('.btn');
                if (autoRefresh) {
                    button.textContent = '🔄 Refresh (Auto)';
                    startLogStream();
                } else {
                    button.textContent = '⏸️ Paused';
                    const status = document.getElementById('connectionStatus');
                    if (status) {
                        status.textContent = '⏸️ Paused';
                        status.style.color = '#ff9800';
                    }
                }
            }
            
            // Update controls
            document.addEventListener('DOMContentLoaded', function() {
                const refreshBtn = document.querySelector('.btn');
                refreshBtn.textContent = '🔄 Refresh (Auto)';
                refreshBtn.onclick = toggleAutoRefresh;
            });
            
            // Stats refresh every 5 seconds
            setInterval(() => {
                if (autoRefresh) {
                    fetchStats();
                }
            }, 5000);
            
            // Initial load
            fetchStats();
            fetchLogs();
            startLogStream();
            
            // Cleanup on page unload
            window.addEventListener('beforeunload', function() {
                autoRefresh = false;
            });
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@router.get("/stats")
async def get_performance_stats(username: str = Depends(get_docs_credentials)):
    """Get current performance statistics"""
    try:
        stats = performance_monitor.get_stats()
        system_stats = performance_monitor.get_system_stats()
        
        return {
            **stats,
            **system_stats,
            "status": "healthy" if stats["error_rate"] < 0.1 else "warning"
        }
    except Exception as e:
        logger.error(f"Error getting performance stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get performance statistics")

@router.get("/recent")
async def get_recent_logs(
    limit: int = Query(50, ge=1, le=1000),
    level: Optional[str] = Query(None),
    username: str = Depends(get_docs_credentials)
):
    """Get recent log entries"""
    try:
        # This is a simplified version - in production, you'd want to read from actual log files
        # or use a proper logging database
        logs = []
        
        # For demo purposes, return some sample logs
        import datetime
        sample_logs = [
            {
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "level": "INFO",
                "module": "unitrust_api",
                "message": "Application started successfully"
            },
            {
                "timestamp": (datetime.datetime.now() - datetime.timedelta(seconds=30)).strftime("%Y-%m-%d %H:%M:%S"),
                "level": "INFO",
                "module": "unitrust_api.middleware",
                "message": "Request processed: GET /healthz"
            },
            {
                "timestamp": (datetime.datetime.now() - datetime.timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S"),
                "level": "WARNING",
                "module": "unitrust_api.performance",
                "message": "High memory usage detected: 85.2%"
            }
        ]
        
        # Filter by level if specified
        if level:
            sample_logs = [log for log in sample_logs if log["level"].lower() == level.lower()]
        
        return sample_logs[:limit]
        
    except Exception as e:
        logger.error(f"Error getting recent logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to get recent logs")

@router.get("/download")
async def download_logs(username: str = Depends(get_docs_credentials)):
    """Download log files"""
    try:
        log_file = os.getenv("LOG_FILE", "logs/unitrust_api.log")
        
        if not os.path.exists(log_file):
            raise HTTPException(status_code=404, detail="Log file not found")
        
        from fastapi.responses import FileResponse
        return FileResponse(
            path=log_file,
            filename=f"unitrust_api_logs_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            media_type="text/plain"
        )
        
    except Exception as e:
        logger.error(f"Error downloading logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to download logs")

@router.post("/health-check")
async def trigger_health_check(username: str = Depends(get_docs_credentials)):
    """Trigger a manual health check"""
    try:
        log_system_health()
        return {"message": "Health check completed", "status": "success"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail="Health check failed")

@router.post("/test")
async def test_logs(username: str = Depends(get_docs_credentials)):
    """Generate test logs for real-time testing"""
    logger = get_logger("unitrust_api.test")
    
    # Generate various types of logs
    logger.info("🧪 Test log generated - INFO level")
    logger.warning("⚠️ Test log generated - WARNING level")
    logger.error("❌ Test log generated - ERROR level")
    logger.debug("🔍 Test log generated - DEBUG level")
    
    # Generate some performance logs
    logger.info("📊 Performance test: CPU usage 45.2%, Memory usage 67.8%")
    logger.info("🔄 Request processed: POST /logs/test - Status: 200 - Time: 0.123s")
    
    return {"message": "Test logs generated successfully", "count": 6}
