# app/main.py
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict
from io import BytesIO
import re, requests, datetime, os

app = FastAPI(title="Underwriting & Returns Extractor - Local (robusto)")

# ======================================================
# ================== CONFIG / HELPERS ==================
# ======================================================

# Destination (Bubble) and authentication
BUBBLE_URL = os.getenv("BUBBLE_URL")  # e.g.: https://solidapps-76096.bubbleapps.io/version-test/api/1.1/wf/unitrust-json/initialize
BUBBLE_TOKEN = os.getenv("BUBBLE_TOKEN")  # token for Authorization: Bearer <token>

# Upload limit (MB)
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))  # default 20 MB

async def read_upload_with_limit(file: UploadFile, max_mb: int = MAX_UPLOAD_MB) -> bytes:
    """
    Reads the file in chunks and returns bytes; raises HTTP 413 if it exceeds the limit.
    """
    max_bytes = max_mb * 1024 * 1024
    chunk_size = 1024 * 1024  # 1 MB
    size = 0
    buf = bytearray()

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Arquivo excede o limite de {max_mb} MB."
            )
        buf.extend(chunk)

    await file.close()
    return bytes(buf)

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
    (?P<name>[A-Z0-9 .,'\-&/]+?)\s+                      # name (1+ espaco)
    (?P<plan>[A-Z0-9\-]+)\s+                             # plan
    (?P<premium>[\d,]+\.\d{2})\s+                        # premium
    (?P<agent_id>\d{6,7})\s+                             # agent id
    (?P<agent>[A-Z0-9 .,'\-&/]+?)\s*$                    # agent
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
    # optional: override destination/credentials via form
    forward_url: Optional[str] = Form(None),
    bearer: Optional[str] = Form("unitrust-7ccc52a2-d463-40ca-a414-23601eb28c80"),
    basic: Optional[str] = Form(None),
    return_text_sample: Optional[str] = Form(None)
):
    if not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo .pdf")

    # reads with limit + file metadata
    content: bytes = await read_upload_with_limit(pdf, MAX_UPLOAD_MB)
    size_bytes = len(content)
    file_meta = {
        "name": pdf.filename,
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2),
        "content_type": pdf.content_type or "application/pdf",
    }

    text = extract_text_from_bytes(content)
    report_date = extract_report_date_iso(text)
    data = parse_report(text)

    if report_date:
        for it in data:
            it["report_date"] = report_date

    # default payload for Bubble
    bubble_payload = {
        "report_type": "underwriting",
        "document_type": document_type,
        "report_date": report_date,
        "count": len(data),
        "items": data
    }

    dest_url = (forward_url or BUBBLE_URL)
    auth_bearer = (bearer or BUBBLE_TOKEN)
    forwarded = None
    if dest_url:
        forwarded = forward_to_url(bubble_payload, dest_url, auth_bearer, basic)

    resp = {
        "document_type": document_type,
        "count": len(data),
        "report_date": report_date,
        "file": file_meta,
        "items": data,
        "forwarded": forwarded
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
    # try a line that contains "DAILY RETURN DRAFT"
    for line in text.splitlines()[:30]:
        if "DAILY RETURN DRAFT" in line.upper():
            m = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', line)
            if m:
                return _ret_date_iso(m.group(1))
    # fallback: first date at the beginning of the file
    m2 = re.search(r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b', text[:500])
    return _ret_date_iso(m2.group(1)) if m2 else None

REASON_START = {
    "NSF","RETURN","PAYMENT","NO","ACCT","ACCOUNT","CUSTOMER","CUST","NOT",
    "UNABLE","LOCATE","LOCAT","INVALID","REFER","STOPPED","CLOSED","CODE",
    "NUMBER","AUTH","R98"
}

def parse_return_items(text: str) -> Dict[str, List[Dict]]:
    """
    Returns {"returned_items": [...], "returned_pre_notes": [...]}
    Each item:
      company_code, policy_no, insured_name, bill_day, issue_date, bill_no,
      amount, agency_code_line, agent_num, agent_name, reason,
      page_region_code, page_region_desc, page_agency_code, page_agency_desc
    """
    returned_items: List[Dict] = []
    returned_pre_notes: List[Dict] = []

    current_region_code: Optional[str] = None
    current_region_desc: Optional[str] = None
    current_agency_code: Optional[str] = None
    current_agency_desc: Optional[str] = None
    section = None  # "RETURNED ITEMS" | "RETURNED PRE-NOTES" | None

    lines = text.splitlines()
    for ln in lines:
        u = ln.upper().strip()

        # page header
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

        # detect section
        if "RETURNED ITEMS" in u:
            section = "RETURNED ITEMS"
            continue
        if "RETURNED PRE-NOTES" in u or "RETURNED PRE NOTES" in u:
            section = "RETURNED PRE-NOTES"
            continue

        # item line (starts with COMPANY + POLICY)
        m = re.match(r'^\s*(\d{3})\s+(\d{10}[A-Z]?)\s+(.+)$', ln)
        if not m:
            continue

        company_code = m.group(1)
        policy_no = m.group(2)
        rest = m.group(3).strip()
        tokens = re.split(r'\s+', rest)
        if len(tokens) < 8:
            continue

        # locate BILL DAY + ISSUE DATE (pattern: 2 digits + date)
        idx = None
        for i in range(0, len(tokens) - 1):
            if re.fullmatch(r'\d{2}', tokens[i]) and re.fullmatch(r'\d{2}/\d{2}/\d{2,4}', tokens[i + 1]):
                idx = i
                break
        if idx is None:
            continue

        insured_name = " ".join(tokens[:idx]).title()
        bill_day = tokens[idx]
        issue_date = _ret_date_iso(tokens[idx + 1])
        bill_no = tokens[idx + 2] if idx + 2 < len(tokens) else None

        # amount
        amount = None
        raw_amount = tokens[idx + 3] if idx + 3 < len(tokens) else None
        if raw_amount is not None:
            if re.fullmatch(r'[\d,]*\.\d{2}', raw_amount) or raw_amount == ".00":
                try:
                    amount = float(raw_amount.replace(",", "")) if raw_amount != ".00" else 0.0
                except Exception:
                    amount = None

        agency_code_line = tokens[idx + 4] if idx + 4 < len(tokens) else None
        agent_num = tokens[idx + 5] if idx + 5 < len(tokens) else None

        # split agent_name vs reason
        rest2 = tokens[idx + 6:]
        reason_idx = None
        for k, tok in enumerate(rest2):
            t = tok.upper()
            if t in REASON_START or re.fullmatch(r'R\d{2}', t):
                reason_idx = k
                break
        if reason_idx is None:
            agent_name = " ".join(rest2[:-1]).title() if rest2 else None
            reason = (rest2[-1].upper() if rest2 else None)
        else:
            agent_name = " ".join(rest2[:reason_idx]).title() if reason_idx > 0 else None
            reason = " ".join(rest2[reason_idx:]).upper()

        item = {
            "section": section,
            "company_code": company_code,
            "policy_no": policy_no,
            "insured_name": insured_name,
            "bill_day": bill_day,
            "issue_date": issue_date,
            "bill_no": bill_no,
            "amount": amount,
            "agency_code_line": agency_code_line,
            "agent_num": agent_num,
            "agent_name": agent_name,
            "reason": reason,
            "page_region_code": current_region_code,
            "page_region_desc": current_region_desc,
            "page_agency_code": current_agency_code,
            "page_agency_desc": current_agency_desc,
        }

        if section == "RETURNED PRE-NOTES":
            returned_pre_notes.append(item)
        else:
            returned_items.append(item)

    return {"returned_items": returned_items, "returned_pre_notes": returned_pre_notes}

# -------------------- /returns (RETURN DRAFTS) --------------------
@app.post("/returns", tags=["returns"])
async def extract_returns(
    pdf: UploadFile = File(...),
    document_type: str = Form(...),
    # optional: override destination/credentials via form
    forward_url: Optional[str] = Form(None),
    bearer: Optional[str] = Form("unitrust-7ccc52a2-d463-40ca-a414-23601eb28c80"),
    basic: Optional[str] = Form(None),
    return_text_sample: Optional[str] = Form(None)
):
    if not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo .pdf")

    # reads with limit + file metadata
    content: bytes = await read_upload_with_limit(pdf, MAX_UPLOAD_MB)
    size_bytes = len(content)
    file_meta = {
        "name": pdf.filename,
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2),
        "content_type": pdf.content_type or "application/pdf",
    }

    text = extract_text_from_bytes(content)
    report_date = extract_return_report_date_iso(text)
    parsed = parse_return_items(text)

    # attach report_date to each item
    for lst in parsed.values():
        for it in lst:
            it["report_date"] = report_date

    counts = {
        "returned_items": len(parsed["returned_items"]),
        "returned_pre_notes": len(parsed["returned_pre_notes"]),
        "total": len(parsed["returned_items"]) + len(parsed["returned_pre_notes"]),
    }

    # default payload for Bubble
    bubble_payload = {
        "report_type": "returns",
        "document_type": document_type,
        "report_date": report_date,
        "count": counts,
        "returned_items": parsed["returned_items"],
        "returned_pre_notes": parsed["returned_pre_notes"]
    }

    dest_url = (forward_url or BUBBLE_URL)
    auth_bearer = (bearer or BUBBLE_TOKEN)
    forwarded = None
    if dest_url:
        forwarded = forward_to_url(bubble_payload, dest_url, auth_bearer, basic)

    resp = {
        "document_type": document_type,
        "report_date": report_date,
        "count": counts,
        "file": file_meta,
        "items": parsed,
        "forwarded": forwarded
    }
    if (return_text_sample or "").strip().lower() in ("1", "true", "yes"):
        resp["text_sample"] = text[:1500]
        resp["text_len"] = len(text)
    return JSONResponse(resp)