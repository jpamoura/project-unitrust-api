# app/services/file_service.py
import datetime
import requests
from typing import Dict, Optional, Tuple, List
from fastapi import HTTPException
from ..config import X_PARSE_APPLICATION_ID, X_PARSE_MASTER_KEY, BACK4APP_FILES_URL, BACK4APP_CSV_CLASS_URL
from ..utils.helpers import normalize_filename, get_current_utc_time

# In-memory cache to temporarily store files between preview and confirmation.
# WARNING: This cache is lost if the server restarts. For production, use a more robust cache like Redis.
upload_cache: Dict[str, Dict] = {}

async def cache_upload(filename: str, content: bytes, content_type: str) -> str:
    """Cache upload data and return a token"""
    import uuid
    token = str(uuid.uuid4())
    upload_cache[token] = {
        "filename": filename,
        "content": content,
        "content_type": content_type,
        "cached_at": get_current_utc_time()
    }
    return token

async def upload_file_to_back4app(filename: str, content: bytes, content_type: Optional[str]) -> Tuple[Dict, Dict]:
    """Upload file to Back4App and create class entry"""
    # Normalize filename to avoid issues with special characters
    normalized_filename = normalize_filename(filename)
    
    upload_headers = {
        'X-Parse-Application-Id': X_PARSE_APPLICATION_ID,
        'X-Parse-Master-Key': X_PARSE_MASTER_KEY,
        'Content-Type': content_type or 'text/csv'
    }
    file_upload_url = f"{BACK4APP_FILES_URL}/{normalized_filename}"
    try:
        upload_response = requests.post(file_upload_url, data=content, headers=upload_headers, timeout=30)
        upload_response.raise_for_status()
        upload_result = upload_response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file to Back4app: {e}")

    class_headers = {
        'X-Parse-Application-Id': X_PARSE_APPLICATION_ID,
        'X-Parse-Master-Key': X_PARSE_MASTER_KEY,
        'Content-Type': 'application/json'
    }
    utc_now = datetime.datetime.utcnow()
    payload = {
        "name_file": normalized_filename,
        "date": {"__type": "Date", "iso": utc_now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'},
        "file": {"__type": "File", "name": upload_result.get("name"), "url": upload_result.get("url")}
    }
    try:
        class_response = requests.post(BACK4APP_CSV_CLASS_URL, json=payload, headers=class_headers, timeout=15)
        class_response.raise_for_status()
        class_result = class_response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to create object in Csv class: {e}")
        
    return upload_result, class_result

def get_cached_upload(token: str) -> Optional[Dict]:
    """Get cached upload data by token"""
    return upload_cache.get(token)

def remove_cached_upload(token: str) -> None:
    """Remove cached upload data by token"""
    if token in upload_cache:
        del upload_cache[token]

def get_last_csv_from_back4app() -> Tuple[List[Dict], Optional[str]]:
    """Get the last CSV file from Back4App"""
    class_headers = {
        'X-Parse-Application-Id': X_PARSE_APPLICATION_ID,
        'X-Parse-Master-Key': X_PARSE_MASTER_KEY,
    }
    params = {'order': '-createdAt', 'limit': 1}

    try:
        resp = requests.get(BACK4APP_CSV_CLASS_URL, headers=class_headers, params=params, timeout=15)
        resp.raise_for_status()
        files_metadata = resp.json().get('results', [])
        return files_metadata, None
    except Exception as e:
        return [], f"Error fetching last file from Back4app: {e}"
