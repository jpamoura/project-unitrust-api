# app/routes/csv_routes.py
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional, Dict
from ..models import ConfirmPayload
from ..parsers.csv_parser import parse_csv_robust, compare_files_as_json_sync
from ..services.file_service import cache_upload, get_cached_upload, remove_cached_upload, upload_file_to_back4app, get_last_csv_from_back4app
from ..utils.helpers import read_upload_with_limit, parse_custom_data_field, forward_to_url, get_current_utc_time
from ..config import BUBBLE_URL, BUBBLE_TOKEN

router = APIRouter(prefix="/compare", tags=["CSV Comparison"])

def _process_preview_and_forward(
    upload_token: str,
    csv_filename: str,
    content_bytes: bytes,
    custom: Optional[Dict],
    dest_url: Optional[str],
    auth_bearer: Optional[str],
    basic: Optional[str]
) -> None:
    """
    Runs in background:
    - Fetch last CSV from Parse
    - Run comparison (or 'first file')
    - Forward everything via forward_to_url (includes custom_data and token)
    """
    if not dest_url:
        return  # nothing to send

    try:
        content_str = content_bytes.decode('utf-8', errors='replace')
        size_bytes = len(content_bytes)
        file_meta = {
            "name": csv_filename,
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / (1024 * 1024), 2),
            "content_type": "text/csv",
            "cached_at": get_current_utc_time()
        }

        # get last file from Parse
        files_metadata, parse_error = get_last_csv_from_back4app()

        payload = {
            "event": "csv_preview_processed",
            "upload_token": upload_token,
            "file": file_meta,
            "custom_data": custom,
            "processed_at": get_current_utc_time()
        }

        if files_metadata:
            old_file_meta = files_metadata[0]
            result = compare_files_as_json_sync(content_str, old_file_meta, new_filename=csv_filename)
            if isinstance(result, dict):
                payload.update(result)
            else:
                payload.update({"error": "Unknown comparison error"})
        else:
            # first file flow
            try:
                data_list = parse_csv_robust(content_str)
                payload.update({
                    "message": "First file: no previous CSV to compare.",
                    "comparison_summary": {
                        "new_file": csv_filename,
                        "old_file": None,
                        "added_count": len(data_list),
                        "removed_count": 0,
                        "modified_count": 0
                    },
                    "added_policies": data_list,
                    "removed_policies": [],
                    "modified_policies": []
                })
            except Exception as e:
                payload.update({"error": f"Error processing the first CSV file: {e}"})

        if parse_error:
            payload["parse_lookup_warning"] = parse_error

        forward_to_url(payload, dest_url, auth_bearer, basic, timeout=30)

    except Exception as e:
        # Try to forward a crash report
        try:
            forward_to_url({
                "event": "csv_preview_processed",
                "upload_token": upload_token,
                "error": f"Background worker crashed: {type(e).__name__} - {e}",
                "custom_data": custom
            }, dest_url, auth_bearer, basic, timeout=15)
        except Exception:
            pass

@router.post("/preview")
async def preview_csv_comparison(
    background_tasks: BackgroundTasks,
    csv_file: UploadFile = File(...),
    custom_data: Optional[str] = Form(None),
    forward_url: Optional[str] = Form(None),
    bearer: Optional[str] = Form(None),
    basic: Optional[str] = Form(None),
):
    if not csv_file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please send a .csv file")

    # read & close fast
    content_bytes = await read_upload_with_limit(csv_file)
    await csv_file.close()

    # cache for later confirmation
    token = await cache_upload(csv_file.filename, content_bytes, csv_file.content_type or "text/csv")

    # parse custom_data
    custom = parse_custom_data_field(custom_data)

    # schedule full processing + forward in background
    dest_url = (forward_url or BUBBLE_URL)
    auth_bearer = (bearer or BUBBLE_TOKEN)
    background_tasks.add_task(
        _process_preview_and_forward,
        token,
        csv_file.filename,
        content_bytes,
        custom,
        dest_url,
        auth_bearer,
        basic
    )

    # respond immediately with 200 OK
    return JSONResponse({"ok": True})

@router.post("/confirm")
async def confirm_csv_upload(
    payload: ConfirmPayload,
    background_tasks: BackgroundTasks
):
    token = payload.upload_token
    
    cached_data = get_cached_upload(token)
    if not cached_data:
        raise HTTPException(status_code=404, detail="Upload token is invalid or has expired.")

    filename = cached_data["filename"]
    content = cached_data["content"]
    content_type = cached_data["content_type"]
    
    upload_result, class_result = await upload_file_to_back4app(filename, content, content_type)

    remove_cached_upload(token)

    # forward in background with upload results + custom_data echoed
    dest_url = payload.forward_url or BUBBLE_URL
    auth_bearer = payload.bearer or BUBBLE_TOKEN
    if dest_url:
        background_tasks.add_task(
            forward_to_url,
            {
                "event": "csv_confirmed",
                "upload_token": token,
                "file_upload_response": upload_result,
                "class_creation_response": class_result,
                "custom_data": payload.custom_data,
                "confirmed_at": get_current_utc_time()
            },
            dest_url,
            auth_bearer,
            payload.basic
        )

    # quick response
    return JSONResponse({
        "message": "File confirmed and saved successfully to Back4app!",
        "ok": True
    })
