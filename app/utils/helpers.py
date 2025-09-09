# app/utils.py
import json
import re
import datetime
import uuid
from typing import Optional, Dict, Any
from fastapi import HTTPException, UploadFile
from ..config import MAX_UPLOAD_MB
from ..models import ForwardResponse

def parse_custom_data_field(custom_data_field: Optional[str]) -> Optional[Dict]:
    """
    Try to parse a string (multipart form field) as JSON.
    - If JSON dict, return it.
    - If JSON but not dict (list/number), wrap as {"value": <obj>}.
    - If not JSON, return {"_raw": <original string>}.
    - If None/empty, return None.
    """
    if not custom_data_field:
        return None
    try:
        obj = json.loads(custom_data_field)
        if isinstance(obj, dict):
            return obj
        return {"value": obj}
    except Exception:
        return {"_raw": custom_data_field}

async def read_upload_with_limit(file: UploadFile, max_mb: int = MAX_UPLOAD_MB) -> bytes:
    """
    Reads the file content and returns bytes; raises HTTP 413 if it exceeds the limit.
    """
    max_bytes = max_mb * 1024 * 1024
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the limit of {max_mb} MB."
        )
    return content

def forward_to_url(payload: dict, url: str, bearer: Optional[str] = None, basic: Optional[str] = None, timeout: int = 20) -> ForwardResponse:
    """
    Sends JSON payload to 'url' with appropriate headers.
    Returns a dict with status/body for logging in the response.
    """
    import requests
    
    headers = {"Content-Type": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    elif basic:
        headers["Authorization"] = "Basic " + basic

    try:
        r = requests.post(url.strip(), json=payload, headers=headers, timeout=timeout)
        return ForwardResponse(status_code=r.status_code, body=(r.text[:400] if r.text else ""))
    except Exception as e:
        return ForwardResponse(error=str(e))

def date_to_iso(raw: str) -> Optional[str]:
    """Convert date string to ISO format"""
    raw = raw.strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            dt = datetime.datetime.strptime(raw, fmt).date()
            return dt.isoformat()
        except Exception:
            pass
    return None

def to_float_premium(s: str) -> Optional[float]:
    """Convert string to float, handling commas"""
    try:
        return float(s.replace(",", ""))
    except Exception:
        return None

def normalize_filename(filename: str) -> str:
    """
    Normalizes the filename to be compatible with URLs and file systems.
    Removes special characters and replaces them with safe characters.
    """
    if not filename:
        return "file.csv"
    
    # Remove extension temporarily
    import os
    name, ext = os.path.splitext(filename)
    
    # Normalize name: remove special characters, replace spaces with underscores
    normalized_name = re.sub(r'[^\w\-_.]', '_', name)
    normalized_name = re.sub(r'_+', '_', normalized_name)  # Remove duplicate underscores
    normalized_name = normalized_name.strip('_')  # Remove underscores from start/end
    
    # If name is empty, use a default name
    if not normalized_name:
        normalized_name = "file"
    
    # Add timestamp to avoid conflicts
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    normalized_name = f"{normalized_name}_{timestamp}"
    
    # Return with extension
    return f"{normalized_name}{ext}"

def is_valid_policy_number(policy: str) -> bool:
    """
    Checks if a policy number is valid.
    Valid policies are ONLY 9-10 digit numbers, optionally followed by a letter.
    Anything that is not a number is considered invalid.
    """
    if not policy or not isinstance(policy, str):
        return False
    
    policy = policy.strip()
    
    # ONLY accepts 9-10 digit numbers, optionally followed by a letter
    # Anything else is considered invalid
    return bool(re.match(r'^\d{9,10}[A-Z]?$', policy))

def generate_upload_token() -> str:
    """Generate a unique upload token"""
    return str(uuid.uuid4())

def get_current_utc_time() -> str:
    """Get current UTC time in ISO format"""
    return datetime.datetime.utcnow().isoformat() + "Z"
