# app/routes/returns_routes.py
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional
from ..parsers.returns_parser import extract_return_report_date_iso, parse_return_items
from ..services.text_extraction_service import extract_text_from_bytes
from ..utils.helpers import read_upload_with_limit, parse_custom_data_field, forward_to_url
from ..config import BUBBLE_URL, BUBBLE_TOKEN, DEFAULT_BEARER

router = APIRouter(prefix="/returns", tags=["returns"])

@router.post("")
async def extract_returns(
    pdf: UploadFile = File(...), 
    document_type: str = Form(...),
    forward_url: Optional[str] = Form(None),
    bearer: Optional[str] = Form(DEFAULT_BEARER),
    basic: Optional[str] = Form(None),
    return_text_sample: Optional[str] = Form(None),
    custom_data: Optional[str] = Form(None),
):
    if not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please send a .pdf file")

    content: bytes = await read_upload_with_limit(pdf)
    await pdf.close()
    
    file_meta = {
        "name": pdf.filename, "size_bytes": len(content),
        "size_mb": round(len(content) / (1024 * 1024), 2),
        "content_type": pdf.content_type or "application/pdf",
    }

    text = extract_text_from_bytes(content)
    report_date = extract_return_report_date_iso(text)
    parsed = parse_return_items(text)

    for lst in parsed.values():
        for it in lst:
            it["report_date"] = report_date

    counts = {
        "returned_items": len(parsed["returned_items"]),
        "returned_pre_notes": len(parsed["returned_pre_notes"]),
        "total": len(parsed["returned_items"]) + len(parsed["returned_pre_notes"]),
    }

    custom = parse_custom_data_field(custom_data)

    bubble_payload = {
        "report_type": "returns", "document_type": document_type, "report_date": report_date,
        "count": counts, "returned_items": parsed["returned_items"], "returned_pre_notes": parsed["returned_pre_notes"],
        "custom_data": custom,
    }

    dest_url = (forward_url or BUBBLE_URL)
    auth_bearer = (bearer or BUBBLE_TOKEN)
    forwarded = None
    if dest_url:
        forwarded = forward_to_url(bubble_payload, dest_url, auth_bearer, basic, timeout=30)

    resp = {
        "document_type": document_type, "report_date": report_date, "count": counts,
        "file": file_meta, "items": parsed, "forwarded": forwarded,
        "custom_data": custom,
    }
    if (return_text_sample or "").strip().lower() in ("1", "true", "yes"):
        resp["text_sample"] = text[:1500]
        resp["text_len"] = len(text)
    return JSONResponse(resp)
