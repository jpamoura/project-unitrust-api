from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict
from io import BytesIO
import re, datetime, requests

app = FastAPI(title="Return Drafts Extractor")

# ----------------------------
# EXTRAÇÃO DE TEXTO (pdfplumber -> PyMuPDF -> PyPDF2)
# ----------------------------
def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    text = ""
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for p in pdf.pages:
                pages.append(p.extract_text() or "")
        text = "\n".join(pages)
    except Exception:
        text = ""

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

    for ch in ["\u00A0", "\u2007", "\u202F"]:
        text = text.replace(ch, " ")
    return text.replace("\t", "    ")

# ----------------------------
# DATAS
# ----------------------------
def _date_iso(s: str) -> Optional[str]:
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass
    return None

def extract_report_date_iso(text: str) -> Optional[str]:
    # típico: "... DAILY RETURN DRAFTS REPORT ... 08/22/2025"
    for line in text.splitlines()[:30]:
        if "DAILY RETURN DRAFTS REPORT" in line.upper():
            m = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', line)
            if m: return _date_iso(m.group(1))
    m2 = re.search(r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b', text[:500])
    return _date_iso(m2.group(1)) if m2 else None

# ----------------------------
# PARSER
# ----------------------------
REASON_START = {
    "NSF","RETURN","PAYMENT","NO","ACCT","ACCOUNT","CUSTOMER","CUST","NOT",
    "UNABLE","LOCATE","LOCAT","INVALID","REFER","STOPPED","CLOSED","CODE","NUMBER","AUTH","R98"
}

def parse_return_items(text: str) -> Dict[str, List[Dict]]:
    """
    Retorna dict com duas listas: {"returned_items": [...], "returned_pre_notes": [...]}
    """
    returned_items: List[Dict] = []
    returned_pre_notes: List[Dict] = []

    current_region_code: Optional[str] = None
    current_region_desc: Optional[str] = None
    current_agency_code_h: Optional[str] = None
    current_agency_desc: Optional[str] = None
    section = None  # "RETURNED ITEMS" | "RETURNED PRE-NOTES" | None

    lines = text.splitlines()
    for ln in lines:
        u = ln.upper().strip()

        # Cabeçalhos (REGION / AGENCY mudam por página)
        m = re.match(r'^\s*REGION:\s+([A-Z]{2})\s+(\d+)-(.+?)\s*$', ln)
        if m:
            current_region_code = m.group(1)
            current_region_desc = m.group(3).strip()
            continue
        m = re.match(r'^\s*AGENCY:\s+([A-Z]{2}\d{3})\s+(\d+)-(.+?)\s*$', ln)
        if m:
            current_agency_code_h = m.group(1)
            current_agency_desc = m.group(3).strip()
            continue

        # Seção
        if "RETURNED ITEMS" in u:
            section = "RETURNED ITEMS"
            continue
        if "RETURNED PRE-NOTES" in u or "RETURNED PRE NOTES" in u:
            section = "RETURNED PRE-NOTES"
            continue

        # Linha de item: começa com "COM POLICY" -> ex: "110 0107680260 ..."
        m = re.match(r'^\s*(\d{3})\s+(\d{10}[A-Z]?)\s+(.+)$', ln)
        if not m:
            continue

        company_code = m.group(1)
        policy_no = m.group(2)
        rest = m.group(3).strip()
        tokens = re.split(r'\s+', rest)
        if len(tokens) < 8:
            continue

        # localizar BILL DAY + ISSUE DATE
        idx = None
        for i in range(0, len(tokens) - 1):
            if re.fullmatch(r'\d{2}', tokens[i]) and re.fullmatch(r'\d{2}/\d{2}/\d{2,4}', tokens[i + 1]):
                idx = i
                break
        if idx is None:
            continue

        insured_name = " ".join(tokens[:idx]).title()
        bill_day = tokens[idx]
        issue_date = _date_iso(tokens[idx + 1])
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

        # separar AGENT NAME x REASON
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
            "page_agency_code": current_agency_code_h,
            "page_agency_desc": current_agency_desc,
        }

        if section == "RETURNED PRE-NOTES":
            returned_pre_notes.append(item)
        else:
            returned_items.append(item)

    return {"returned_items": returned_items, "returned_pre_notes": returned_pre_notes}

# ----------------------------
# ENDPOINT
# ----------------------------
@app.post("/extract/returns")
async def extract_returns(
    pdf: UploadFile = File(...),
    forward_url: Optional[str] = Form(None),
    return_text_sample: Optional[str] = Form(None),
    bearer: Optional[str] = Form(None),
    basic: Optional[str] = Form(None),
):
    if not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo .pdf")

    content: bytes = await pdf.read()
    text = extract_text_from_bytes(content)
    report_date = extract_report_date_iso(text)
    parsed = parse_return_items(text)

    # anexa report_date em cada item
    for lst in parsed.values():
        for it in lst:
            it["report_date"] = report_date

    # encaminhar (opcional)
    forwarded = None
    if forward_url and forward_url.strip():
        headers = {"Content-Type": "application/json"}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        elif basic:
            headers["Authorization"] = "Basic " + basic
        try:
            r = requests.post(forward_url.strip(), headers=headers, json=parsed, timeout=30)
            forwarded = {"status_code": r.status_code, "body": r.text[:400]}
        except Exception as e:
            forwarded = {"error": str(e)}

    resp = {
        "report_date": report_date,
        "count": {
            "returned_items": len(parsed["returned_items"]),
            "returned_pre_notes": len(parsed["returned_pre_notes"]),
            "total": len(parsed["returned_items"]) + len(parsed["returned_pre_notes"]),
        },
        "items": parsed,
        "forwarded": forwarded
    }
    if (return_text_sample or "").strip().lower() in ("1", "true", "yes"):
        resp["text_sample"] = text[:1500]
        resp["text_len"] = len(text)
    return JSONResponse(resp)
