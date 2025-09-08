# app/main.py
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
from io import BytesIO, StringIO
import re, requests, datetime, os, uuid, csv
import pandas as pd
import numpy as np

app = FastAPI(title="Underwriting & Returns Extractor - Local (robusto)")

# ======================================================
# ================== CONFIG / HELPERS ==================
# ======================================================

# Destination (Bubble) and authentication
BUBBLE_URL = os.getenv("BUBBLE_URL")  # e.g.: https://solidapps-76096.bubbleapps.io/version-test/api/1.1/wf/unitrust-json/initialize
BUBBLE_TOKEN = os.getenv("BUBBLE_TOKEN")  # token for Authorization: Bearer <token>

# Back4App Credentials
X_PARSE_APPLICATION_ID = os.getenv("X_PARSE_APPLICATION_ID", "tETk6wll2qxSh2OXxBWaLDh9ZjyGEvI9VppCVOe7")
X_PARSE_MASTER_KEY = os.getenv("X_PARSE_MASTER_KEY", "hAXjwSLgl7c2XlvL9gaPEhPcZbfbWvQ54um0EiOG")

# Back4app URLs
BACK4APP_FILES_URL = os.getenv("BACK4APP_FILES_URL", "https://parseapi.back4app.com/files")
BACK4APP_CSV_CLASS_URL = os.getenv("BACK4APP_CSV_CLASS_URL", "https://parseapi.back4app.com/classes/Csv")


# Upload limit (MB)
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))  # default 20 MB

# In-memory cache to temporarily store files between preview and confirmation.
# WARNING: This cache is lost if the server restarts. For production, use a more robust cache like Redis.
upload_cache: Dict[str, Dict] = {}


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

def forward_to_url(payload: dict, url: str, bearer: Optional[str] = None, basic: Optional[str] = None, timeout: int = 20) -> dict:
    """
    Sends JSON payload to 'url' with appropriate headers.
    Returns a dict with status/body for logging in the response.
    """
    headers = {"Content-Type": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    elif basic:
        headers["Authorization"] = "Basic " + basic

    try:
        r = requests.post(url.strip(), json=payload, headers=headers, timeout=timeout)
        return {"status_code": r.status_code, "body": (r.text[:400] if r.text else "")}
    except Exception as e:
        return {"error": str(e)}

# ======================================================
# ======== TEXT EXTRACTION (with multiple fallbacks) ===
# ======================================================

def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """
    Extracts text with multiple fallbacks:
    1) pdfplumber (pdfminer)
    2) PyMuPDF (fitz)
    3) PyPDF2
    Normalizes spaces at the end.
    """
    text = ""

    # 1) pdfplumber
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for p in pdf.pages:
                pages.append(p.extract_text() or "")
        text = "\n".join(pages)
    except Exception:
        text = ""

    # 2) PyMuPDF (fitz), if necessary
    if len((text or "").strip()) < 50:
        try:
            import fitz  # PyMuPDF
            pages = []
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                for page in doc:
                    pages.append(page.get_text("text") or "")
            text = "\n".join(pages)
        except Exception:
            pass

    # 3) PyPDF2, if we still didn't get anything useful
    if len((text or "").strip()) < 50:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(BytesIO(pdf_bytes))
            pages = []
            for page in reader.pages:
                pages.append(page.extract_text() or "")
            text = "\n".join(pages)
        except Exception:
            pass

    # final normalization
    for ch in ["\u00A0", "\u2007", "\u202F"]:
        text = text.replace(ch, " ")
    text = text.replace("\t", "    ")
    return text

# ======================================================
# ===============  UNDERWRITING PARSER  ================
# ======================================================

STATUS_HEADERS = [
    "SUBMITTED",
    "UNDERWRITING REQUIREMENTS ADDED",
    "UNDERWRITING REQUIREMENTS UPDATED",
    "ISSUED",
    "DELIVERED",
    "DECLINE",
    "INCOMPLETE",
    "WITHDRAWN",
]

# Accepts 1+ spaces after the name
POLICY_RE = re.compile(
    r"""^\s*(?P<policy>\d{9,10}[A-Z]?)\s+                 # policy
    (?P<name>[A-Z0-9 .,'\-&/]+?)\s+                       # name (1+ espaco)
    (?P<plan>[A-Z0-9\-]+)\s+                              # plan
    (?P<premium>[\d,]+\.\d{2})\s+                         # premium
    (?P<agent_id>\d{6,7})\s+                              # agent id
    (?P<agent>[A-Z0-9 .,'\-&/]+?)\s*$                     # agent
    """,
    re.VERBOSE
)

UW_RE = re.compile(
    r"""^\s*(?P<policy>\d{9,10}[A-Z]?)\s+
    (?P<name>[A-Z0-9 .,'\-&/]+?)\s{2,}
    (?P<requirement>[^-].*?\S)\s{2,}
    (?P<agent_id>\d{6,7})\s+
    (?P<agent>[A-Z0-9 .,'\-&/]+?)\s*$""",
    re.VERBOSE
)

def extract_report_date_iso(text: str) -> Optional[str]:
    """
    Looks for a date like mm/dd/yy (or yyyy) in the header,
    preferring the line with 'DAILY NEW BUSINESS/UNDERWRITING ACTIVITY REPORT'.
    """
    for line in text.splitlines()[:20]:
        m = re.search(
            r'(\d{1,2}/\d{1,2}/\d{2,4})\s+DAILY NEW BUSINESS/UNDERWRITING ACTIVITY REPORT',
            line, flags=re.IGNORECASE
        )
        if m:
            iso = _date_to_iso(m.group(1))
            if iso:
                return iso
    m2 = re.search(r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b', text[:500])
    if m2:
        return _date_to_iso(m2.group(1))
    return None

def _date_to_iso(raw: str) -> Optional[str]:
    raw = raw.strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            dt = datetime.datetime.strptime(raw, fmt).date()
            return dt.isoformat()
        except Exception:
            pass
    return None

def _to_float_premium(s: str):
    try:
        return float(s.replace(",", ""))
    except Exception:
        return None

def _parse_policy_line_by_columns(line: str):
    parts = re.split(r"\s{2,}", line.strip())
    if len(parts) < 6:
        return None
    policy, name, plan, premium, agent_id, agent = parts[:6]
    if not re.match(r"^\d{9,10}[A-Z]?$", policy): return None
    if not re.match(r"^[A-Z0-9\-]+$", plan): return None
    if not re.match(r"^[\d,]+\.\d{2}$", premium): return None
    if not re.match(r"^\d{6,7}$", agent_id): return None
    return {
        "policy_no": policy,
        "insured_name": name.title(),
        "plan": plan,
        "annual_premium": _to_float_premium(premium),
        "agent_id": agent_id,
        "writing_agent": agent.title(),
        "requirement_desc": None,
    }

def _parse_uw_line_by_columns(line: str):
    parts = re.split(r"\s{2,}", line.strip())
    if len(parts) < 5:
        return None
    policy, name, requirement, agent_id, agent = parts[:5]
    if not re.match(r"^\d{9,10}[A-Z]?$", policy): return None
    if not re.match(r"^\d{6,7}$", agent_id): return None
    return {
        "policy_no": policy,
        "insured_name": name.title(),
        "plan": None,
        "annual_premium": None,
        "agent_id": agent_id,
        "writing_agent": agent.title(),
        "requirement_desc": requirement.strip(),
    }

def _parse_policy_line_by_tokens(line: str):
    parts = re.split(r"\s+", line.strip())
    if len(parts) < 6:
        return None
    policy = parts[0]
    if not re.match(r"^\d{9,10}[A-Z]?$", policy):
        return None
    try:
        agent_id_idx = max(i for i, t in enumerate(parts) if re.match(r"^\d{6,7}$", t))
    except ValueError:
        return None
    agent_id = parts[agent_id_idx]
    if agent_id_idx - 1 < 0: return None
    premium = parts[agent_id_idx - 1]
    if not re.match(r"^[\d,]+\.\d{2}$", premium): return None
    if agent_id_idx - 2 < 0: return None
    plan = parts[agent_id_idx - 2]
    if not re.match(r"^[A-Z0-9\-]+$", plan): return None
    name_tokens = parts[1:agent_id_idx - 2]
    if not name_tokens: return None
    name = " ".join(name_tokens)
    agent_tokens = parts[agent_id_idx + 1:]
    if not agent_tokens: return None
    agent = " ".join(agent_tokens)
    return {
        "policy_no": policy,
        "insured_name": name.title(),
        "plan": plan,
        "annual_premium": _to_float_premium(premium),
        "agent_id": agent_id,
        "writing_agent": agent.title(),
        "requirement_desc": None,
    }

def parse_report(text: str) -> List[Dict]:
    out: List[Dict] = []
    status: Optional[str] = None

    def detect_status(line: str) -> Optional[str]:
        u = re.sub(r"\s+", " ", line).strip().upper()
        if not u: return None
        if "UNDERWRITING REQUIREMENTS" in u and "ADDED" in u:   return "UNDERWRITING REQUIREMENTS ADDED"
        if "UNDERWRITING REQUIREMENTS" in u and "UPDATED" in u: return "UNDERWRITING REQUIREMENTS UPDATED"
        if "SUBMITTED" in u:   return "SUBMITTED"
        if "ISSUED" in u:      return "ISSUED"
        if "DELIVERED" in u:   return "DELIVERED"
        if "DECLINE" in u or "DECLINED" in u: return "DECLINE"
        if "INCOMPLETE" in u:  return "INCOMPLETE"
        if "WITHDRAWN" in u:   return "WITHDRAWN"
        return None

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue

        new_status = detect_status(line)
        if new_status:
            status = new_status
            continue

        if status in ("SUBMITTED", "ISSUED", "DELIVERED", "DECLINE", "INCOMPLETE", "WITHDRAWN", "UNKNOWN", None):
            m = POLICY_RE.match(line)
            if m:
                d = m.groupdict()
                out.append({
                    "status": status or "UNKNOWN",
                    "policy_no": d["policy"],
                    "insured_name": d["name"].title(),
                    "plan": d["plan"],
                    "annual_premium": _to_float_premium(d["premium"]),
                    "agent_id": d["agent_id"],
                    "writing_agent": d["agent"].title(),
                    "requirement_desc": None,
                })
                continue

            parsed = _parse_policy_line_by_columns(line)
            if parsed:
                parsed["status"] = status or "UNKNOWN"
                out.append(parsed)
                continue

            parsed = _parse_policy_line_by_tokens(line)
            if parsed:
                parsed["status"] = status or "UNKNOWN"
                out.append(parsed)
                continue

        if status in ("UNDERWRITING REQUIREMENTS ADDED", "UNDERWRITING REQUIREMENTS UPDATED"):
            m = UW_RE.match(line)
            if m:
                d = m.groupdict()
                out.append({
                    "status": status,
                    "policy_no": d["policy"],
                    "insured_name": d["name"].title(),
                    "plan": None,
                    "annual_premium": None,
                    "agent_id": d["agent_id"],
                    "writing_agent": d["agent"].title(),
                    "requirement_desc": d["requirement"].strip(),
                })
                continue

            parsed = _parse_uw_line_by_columns(line)
            if parsed:
                parsed["status"] = status
                out.append(parsed)
                continue

    return out

# ======================================================
# ===================  ENDPOINTS  ======================
# ======================================================

@app.get("/")
def root():
    return {"ok": True, "service": "Underwriting & Returns Extractor - Local (robusto)"}

@app.get("/healthz")
def healthz():
    return {"ok": True}

# -------------------- /extract (UNDERWRITING) --------------------
@app.post("/extract", tags=["underwriting"])
async def extract_underwriting(
    pdf: UploadFile = File(...),
    document_type: str = Form(...),
    forward_url: Optional[str] = Form(None),
    bearer: Optional[str] = Form("unitrust-7ccc52a2-d463-40ca-a414-23601eb28c80"),
    basic: Optional[str] = Form(None),
    return_text_sample: Optional[str] = Form(None)
):
    if not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please send a .pdf file")

    content: bytes = await read_upload_with_limit(pdf)
    await pdf.close()
    
    size_bytes = len(content)
    file_meta = {
        "name": pdf.filename, "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2),
        "content_type": pdf.content_type or "application/pdf",
    }

    text = extract_text_from_bytes(content)
    report_date = extract_report_date_iso(text)
    data = parse_report(text)

    if report_date:
        for it in data:
            it["report_date"] = report_date

    bubble_payload = {
        "report_type": "underwriting", "document_type": document_type, "report_date": report_date,
        "count": len(data), "items": data
    }

    dest_url = (forward_url or BUBBLE_URL)
    auth_bearer = (bearer or BUBBLE_TOKEN)
    forwarded = None
    if dest_url:
        forwarded = forward_to_url(bubble_payload, dest_url, auth_bearer, basic)

    resp = {
        "document_type": document_type, "count": len(data), "report_date": report_date,
        "file": file_meta, "items": data, "forwarded": forwarded
    }
    if (return_text_sample or "").strip().lower() in ("1", "true", "yes"):
        resp["text_sample"] = text[:1500]
        resp["text_len"] = len(text)
    return JSONResponse(resp)

# =========================================================
# ===============  RETURN DRAFTS: parser + API  ===========
# =========================================================

def _ret_date_iso(s: str) -> Optional[str]:
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass
    return None

def extract_return_report_date_iso(text: str) -> Optional[str]:
    for line in text.splitlines()[:30]:
        if "DAILY RETURN DRAFT" in line.upper():
            m = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', line)
            if m:
                return _ret_date_iso(m.group(1))
    m2 = re.search(r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b', text[:500])
    return _ret_date_iso(m2.group(1)) if m2 else None

REASON_START = {
    "NSF","RETURN","PAYMENT","NO","ACCT","ACCOUNT","CUSTOMER","CUST","NOT",
    "UNABLE","LOCATE","LOCAT","INVALID","REFER","STOPPED","CLOSED","CODE",
    "NUMBER","AUTH","R98"
}

def parse_return_items(text: str) -> Dict[str, List[Dict]]:
    returned_items: List[Dict] = []
    returned_pre_notes: List[Dict] = []
    current_region_code: Optional[str] = None
    current_region_desc: Optional[str] = None
    current_agency_code: Optional[str] = None
    current_agency_desc: Optional[str] = None
    section = None

    for ln in text.splitlines():
        u = ln.upper().strip()
        m = re.match(r'^\s*REGION:\s+([A-Z]{2})\s+(\d+)-(.+?)\s*$', ln)
        if m:
            current_region_code = m.group(1)
            current_region_desc = m.group(3).strip()
            continue
        m = re.match(r'^\s*AGENCY:\s+([A-Z]{2}\d{3})\s+(\d+)-(.+?)\s*$', ln)
        if m:
            current_agency_code = m.group(1)
            current_agency_desc = m.group(3).strip()
            continue

        if "RETURNED ITEMS" in u: section = "RETURNED ITEMS"
        elif "RETURNED PRE-NOTES" in u or "RETURNED PRE NOTES" in u: section = "RETURNED PRE-NOTES"

        m = re.match(r'^\s*(\d{3})\s+(\d{10}[A-Z]?)\s+(.+)$', ln)
        if not m: continue

        company_code, policy_no, rest = m.group(1), m.group(2), m.group(3).strip()
        tokens = re.split(r'\s+', rest)
        if len(tokens) < 8: continue

        idx = None
        for i in range(len(tokens) - 1):
            if re.fullmatch(r'\d{2}', tokens[i]) and re.fullmatch(r'\d{2}/\d{2}/\d{2,4}', tokens[i + 1]):
                idx = i
                break
        if idx is None: continue

        insured_name = " ".join(tokens[:idx]).title()
        bill_day = tokens[idx]
        issue_date = _ret_date_iso(tokens[idx + 1])
        bill_no = tokens[idx + 2] if idx + 2 < len(tokens) else None
        
        amount = None
        raw_amount = tokens[idx + 3] if idx + 3 < len(tokens) else None
        if raw_amount and (re.fullmatch(r'[\d,]*\.\d{2}', raw_amount) or raw_amount == ".00"):
            try: amount = float(raw_amount.replace(",", "")) if raw_amount != ".00" else 0.0
            except Exception: amount = None

        agency_code_line = tokens[idx + 4] if idx + 4 < len(tokens) else None
        agent_num = tokens[idx + 5] if idx + 5 < len(tokens) else None

        rest2 = tokens[idx + 6:]
        reason_idx = None
        for k, tok in enumerate(rest2):
            if tok.upper() in REASON_START or re.fullmatch(r'R\d{2}', tok.upper()):
                reason_idx = k
                break
        
        agent_name = " ".join(rest2[:reason_idx]).title() if reason_idx is not None and reason_idx > 0 else (" ".join(rest2[:-1]).title() if rest2 else None)
        reason = " ".join(rest2[reason_idx:]).upper() if reason_idx is not None else (rest2[-1].upper() if rest2 else None)

        item = {
            "section": section, "company_code": company_code, "policy_no": policy_no,
            "insured_name": insured_name, "bill_day": bill_day, "issue_date": issue_date,
            "bill_no": bill_no, "amount": amount, "agency_code_line": agency_code_line,
            "agent_num": agent_num, "agent_name": agent_name, "reason": reason,
            "page_region_code": current_region_code, "page_region_desc": current_region_desc,
            "page_agency_code": current_agency_code, "page_agency_desc": current_agency_desc,
        }
        if section == "RETURNED PRE-NOTES": returned_pre_notes.append(item)
        else: returned_items.append(item)
        
    return {"returned_items": returned_items, "returned_pre_notes": returned_pre_notes}

@app.post("/returns", tags=["returns"])
async def extract_returns(
    pdf: UploadFile = File(...), document_type: str = Form(...),
    forward_url: Optional[str] = Form(None),
    bearer: Optional[str] = Form("unitrust-7ccc52a2-d463-40ca-a414-23601eb28c80"),
    basic: Optional[str] = Form(None),
    return_text_sample: Optional[str] = Form(None)
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

    bubble_payload = {
        "report_type": "returns", "document_type": document_type, "report_date": report_date,
        "count": counts, "returned_items": parsed["returned_items"], "returned_pre_notes": parsed["returned_pre_notes"]
    }

    dest_url = (forward_url or BUBBLE_URL)
    auth_bearer = (bearer or BUBBLE_TOKEN)
    forwarded = None
    if dest_url:
        forwarded = forward_to_url(bubble_payload, dest_url, auth_bearer, basic)

    resp = {
        "document_type": document_type, "report_date": report_date, "count": counts,
        "file": file_meta, "items": parsed, "forwarded": forwarded
    }
    if (return_text_sample or "").strip().lower() in ("1", "true", "yes"):
        resp["text_sample"] = text[:1500]
        resp["text_len"] = len(text)
    return JSONResponse(resp)

# =========================================================
# ================= NEW CSV COMPARISON FLOW ===============
# =========================================================

class ConfirmPayload(BaseModel):
    upload_token: str

@app.post("/compare/preview", tags=["CSV Comparison"])
async def preview_csv_comparison(csv_file: UploadFile = File(...)):
    if not csv_file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please send a .csv file")

    content_bytes = await read_upload_with_limit(csv_file)
    await csv_file.close()
    content_str = content_bytes.decode('utf-8', errors='replace')

    class_headers = {
        'X-Parse-Application-Id': X_PARSE_APPLICATION_ID,
        'X-Parse-Master-Key': X_PARSE_MASTER_KEY,
    }
    params = {'order': '-createdAt', 'limit': 1}
    
    try:
        response = requests.get(BACK4APP_CSV_CLASS_URL, headers=class_headers, params=params)
        response.raise_for_status()
        files_metadata = response.json().get('results', [])
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching last file from Back4app: {e}")

    if not files_metadata:
        token = await cache_upload(csv_file, content_bytes)
        try:
            # Convert CSV to a list of dictionaries using robust parsing
            data_list = parse_csv_robust(content_str)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error processing the first CSV file: {e}")

        return JSONResponse({
            "message": "This is the first file. There is no previous file to compare against.",
            "upload_token": token,
            "comparison_summary": {
                "new_file": csv_file.filename, "old_file": None,
                "added_count": len(data_list), "removed_count": 0, "modified_count": 0,
            },
            "added_policies": data_list,
            "removed_policies": [], "modified_policies": []
        })

    old_file_meta = files_metadata[0]
    comparison_results = await compare_files_as_json(content_str, old_file_meta, new_filename=csv_file.filename)
    token = await cache_upload(csv_file, content_bytes)

    response_data = {
        "message": "Comparison preview generated successfully. Use the token to confirm the upload.",
        "upload_token": token,
        **comparison_results
    }
    return JSONResponse(response_data)


@app.post("/compare/confirm", tags=["CSV Comparison"])
async def confirm_csv_upload(payload: ConfirmPayload):
    token = payload.upload_token
    
    cached_data = upload_cache.get(token)
    if not cached_data:
        raise HTTPException(status_code=404, detail="Upload token is invalid or has expired.")

    filename = cached_data["filename"]
    content = cached_data["content"]
    content_type = cached_data["content_type"]
    
    upload_result, class_result = await upload_file_to_back4app(filename, content, content_type)

    if token in upload_cache:
        del upload_cache[token]

    return JSONResponse({
        "message": "File confirmed and saved successfully to Back4app!",
        "file_upload_response": upload_result,
        "class_creation_response": class_result
    })

# =========================================================
# ================== Helper Functions =====================
# =========================================================

async def cache_upload(file: UploadFile, content: bytes) -> str:
    token = str(uuid.uuid4())
    upload_cache[token] = {
        "filename": file.filename,
        "content": content,
        "content_type": file.content_type,
        "cached_at": datetime.datetime.utcnow().isoformat()
    }
    return token

def normalize_csv_content(content: str) -> str:
    """
    Normalizes CSV content with entire lines in quotes and internal values with double quotes.
    - If the line starts and ends with quotes, remove the outer pair.
    - Converts internal double quotes ("") to single quotes (").
    Keeps the line intact when it's not "doubly" quoted.
    """
    fixed_lines = []
    for ln in content.splitlines():
        if ln.startswith('"') and ln.endswith('"'):
            inner = ln[1:-1].replace('""', '"')
            fixed_lines.append(inner)
        else:
            fixed_lines.append(ln)
    return "\n".join(fixed_lines)

def normalize_filename(filename: str) -> str:
    """
    Normalizes the filename to be compatible with URLs and file systems.
    Removes special characters and replaces them with safe characters.
    """
    if not filename:
        return "file.csv"
    
    # Remove extension temporarily
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

def detect_policy_column(rows: List[Dict]) -> Optional[str]:
    """
    Automatically detects which column contains policy numbers.
    Returns the column name or None if not found.
    """
    if not rows:
        return None
    
    # List of candidates in priority order
    candidates = ['Policy', 'Company', 'PolicyNumber', 'PolicyNo', 'Policy_Number', 'POLICY', 'COMPANY']
    
    # Add all available columns as candidates
    if rows:
        for col_name in rows[0].keys():
            if col_name not in candidates:
                candidates.append(col_name)
    
    best_column = None
    best_score = 0
    
    for candidate in candidates:
        if candidate not in rows[0]:
            continue
            
        valid_count = 0
        total_count = 0
        
        # Check the first 100 rows
        for row in rows[:100]:
            value = row.get(candidate, '')
            if value and isinstance(value, str):
                total_count += 1
                if is_valid_policy_number(value):
                    valid_count += 1
        
        # Calculate score (percentage of valid policies)
        if total_count > 0:
            score = valid_count / total_count
            if score > best_score:
                best_score = score
                best_column = candidate
    
    # Return the column with best score if it has at least 30% valid policies
    if best_score >= 0.3:
        return best_column
    
    return None

def _mostly_in_first_column(rows: List[dict]) -> bool:
    """
    Heuristic: True if most rows have only the first field filled and the rest empty,
    classic symptom of CSV with entire line quoted and/or internal double quotes.
    """
    if not rows:
        return False
    keys = list(rows[0].keys())
    if not keys:
        return False
    first, rest = keys[0], keys[1:]
    bad = 0
    total = min(len(rows), 50)  # sample
    for r in rows[:total]:
        only_first = bool((r.get(first) or "").strip()) and all(not ((r.get(k) or "").strip()) for k in rest)
        if only_first:
            bad += 1
    return bad >= total // 2

def parse_csv_robust(content: str) -> List[Dict]:
    """
    Robust CSV parsing: tries direct parser; if it detects data fell only in the 1st column,
    normalizes by removing external quotes and unfolding internal quotes, then parses again.
    Then, detects the policy column and normalizes the rows.
    """
    import io, csv

    # 1) Try standard parser directly
    try:
        rows = list(csv.DictReader(io.StringIO(content)))
    except Exception:
        rows = []

    # 2) If it failed or everything fell in the first field, normalize and try again
    if not rows or _mostly_in_first_column(rows):
        fixed = normalize_csv_content(content)
        rows = list(csv.DictReader(io.StringIO(fixed)))

    if not rows:
        raise HTTPException(status_code=400, detail="Empty or invalid CSV file")

    # 3) Automatically detect the policy column
    policy_column = detect_policy_column(rows)
    if not policy_column:
        # fallback: try to find first numeric column; otherwise, use the first column
        first_row = rows[0]
        for col_name, value in first_row.items():
            if isinstance(value, str) and value.strip().isdigit():
                policy_column = col_name
                break
        if not policy_column and first_row:
            policy_column = list(first_row.keys())[0]

    # 4) Clean and normalize rows using the policy column
    valid_rows = []
    for row in rows:
        cleaned_row = clean_and_normalize_row_with_policy_column(row, policy_column)
        if cleaned_row is not None:
            valid_rows.append(cleaned_row)

    return valid_rows

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

def clean_and_normalize_row_with_policy_column(row: dict, policy_column: str) -> dict:
    """Cleans keys and values of a dictionary and normalizes the Policy column."""
    cleaned_row = {}
    if row is None:
        return cleaned_row
        
    # Clean keys (column names) and values
    for key, value in row.items():
        clean_key = key.strip() if key else None
        
        clean_value = value
        if isinstance(value, str):
            clean_value = value.strip()
        
        if clean_value == "":
            clean_value = None
            
        if clean_key:
             cleaned_row[clean_key] = clean_value
    
    # Create a standardized 'Policy' column based on the detected column
    # but keeps original data in their correct columns
    if policy_column in cleaned_row:
        cleaned_row['Policy'] = cleaned_row[policy_column]
    
    # Validate if the row has a valid policy
    policy = cleaned_row.get('Policy')
    if policy and not is_valid_policy_number(policy):
        # If it's not a valid policy, but still has valid data, keep the row
        # Only filter if the row is completely empty or invalid
        if not any(v for v in cleaned_row.values() if v and str(v).strip()):
            return None
            
    return cleaned_row
    
def clean_and_normalize_row(row: dict) -> dict:
    """Cleans keys and values of a dictionary representing a CSV row."""
    cleaned_row = {}
    if row is None:
        return cleaned_row
        
    # Clean keys (column names) and values
    for key, value in row.items():
        clean_key = key.strip() if key else None
        
        clean_value = value
        if isinstance(value, str):
            clean_value = value.strip()
        
        if clean_value == "":
            clean_value = None
            
        if clean_key:
             cleaned_row[clean_key] = clean_value
    
    # Validate if the row has a valid policy
    policy = cleaned_row.get('Policy')
    if policy and not is_valid_policy_number(policy):
        # If it's not a valid policy, return None to be filtered
        return None
            
    return cleaned_row

async def compare_files_as_json(new_content_str: str, old_file_meta: dict, new_filename: str) -> dict:
    """
    Converts CSVs to lists of dictionaries and compares them robustly.
    """
    try:
        old_file_url = old_file_meta.get('file', {}).get('url')
        if not old_file_url:
            raise ValueError("Old file URL not found in metadata.")
        
        old_content_bytes = requests.get(old_file_url).content
        old_content_str = old_content_bytes.decode('utf-8', errors='replace')
        
        # Convert CSVs to lists of dictionaries using robust parsing
        list_new = parse_csv_robust(new_content_str)
        list_old = parse_csv_robust(old_content_str)

        # Validate if 'Policy' column exists after cleaning
        if not list_new or 'Policy' not in list_new[0]:
            raise HTTPException(status_code=400, detail="'Policy' column not found in the new file.")
        if not list_old or 'Policy' not in list_old[0]:
             raise HTTPException(status_code=400, detail="'Policy' column not found in the old file.")

        # Create maps for fast lookup using 'Policy' as key
        map_new = {row['Policy']: row for row in list_new if row and row.get('Policy')}
        map_old = {row['Policy']: row for row in list_old if row and row.get('Policy')}

        keys_new = set(map_new.keys())
        keys_old = set(map_old.keys())

        # Find added policies (new)
        added_ids = keys_new - keys_old
        added_policies = [map_new[pid] for pid in added_ids]

        # Find modified policies (exist in both files but have changes)
        common_ids = keys_new.intersection(keys_old)
        modified_policies = []
        
        # Fields to check for changes (all relevant fields)
        fields_to_check = ['WritingAgent', 'AgentName', 'Company', 'Status', 'DOB', 'PolicyDate', 
                          'PaidtoDate', 'RecvDate', 'LastName', 'FirstName', 'MI', 'Plan', 'Face', 
                          'Form', 'Mode', 'ModePrem', 'Address1', 'Address2', 'Address3', 'Address4', 
                          'State', 'Zip', 'Phone', 'Email', 'App Date', 'WrtPct']
        
        for pid in common_ids:
            old_row = map_old[pid]
            new_row = map_new[pid]
            
            # Check if there were changes in any field
            has_changes = False
            changes = {}
            
            for field in fields_to_check:
                old_value = old_row.get(field, '')
                new_value = new_row.get(field, '')
                
                # Normalize values for comparison
                old_normalized = str(old_value).strip().lower() if old_value is not None else ''
                new_normalized = str(new_value).strip().lower() if new_value is not None else ''
                
                # For numeric fields, compare numeric values
                if field in ['Face', 'ModePrem', 'WrtPct']:
                    try:
                        old_num = float(old_normalized.replace(',', '')) if old_normalized else 0
                        new_num = float(new_normalized.replace(',', '')) if new_normalized else 0
                        if abs(old_num - new_num) > 0.01:  # Tolerance for rounding differences
                            has_changes = True
                            changes[field] = {
                                'old_value': old_row.get(field, ''),
                                'new_value': new_row.get(field, '')
                            }
                    except (ValueError, AttributeError):
                        if old_normalized != new_normalized:
                            has_changes = True
                            changes[field] = {
                                'old_value': old_row.get(field, ''),
                                'new_value': new_row.get(field, '')
                            }
                else:
                    # For text fields, compare directly
                    if old_normalized != new_normalized:
                        has_changes = True
                        changes[field] = {
                            'old_value': old_row.get(field, ''),
                            'new_value': new_row.get(field, '')
                        }
            
            if has_changes:
                # Return only the current record from the new file
                modified_policies.append(new_row)
        
        # Combine new and modified records
        all_changes = []
        
        # Add new records
        all_changes.extend(added_policies)
        
        # Add modified records
        all_changes.extend(modified_policies)
        
        return {
            "comparison_summary": {
                "new_file": new_filename, 
                "old_file": old_file_meta.get('name_file'),
                "total_changes": len(all_changes),
                "new_records": len(added_policies),
                "modified_records": len(modified_policies)
            },
            "changes": all_changes
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during JSON data comparison: {type(e).__name__} - {e}")

async def upload_file_to_back4app(filename: str, content: bytes, content_type: Optional[str]):
    # Normaliza o nome do arquivo para evitar problemas com caracteres especiais
    normalized_filename = normalize_filename(filename)
    
    upload_headers = {
        'X-Parse-Application-Id': X_PARSE_APPLICATION_ID,
        'X-Parse-Master-Key': X_PARSE_MASTER_KEY,
        'Content-Type': content_type or 'text/csv'
    }
    file_upload_url = f"{BACK4APP_FILES_URL}/{normalized_filename}"
    try:
        upload_response = requests.post(file_upload_url, data=content, headers=upload_headers)
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
        "name_file": normalized_filename,  # Usa o nome normalizado
        "date": {"__type": "Date", "iso": utc_now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'},
        "file": {"__type": "File", "name": upload_result.get("name"), "url": upload_result.get("url")}
    }
    try:
        class_response = requests.post(BACK4APP_CSV_CLASS_URL, json=payload, headers=class_headers)
        class_response.raise_for_status()
        class_result = class_response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to create object in Csv class: {e}")
        
    return upload_result, class_result
