# app/main.py
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict
from io import BytesIO
import re, json, requests, datetime

app = FastAPI(title="Underwriting Extractor - Local (robusto)")

# ----------------------------
# Status reconhecidos
# ----------------------------
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

# ----------------------------
# Regex principais
# ----------------------------
# Aceita 1+ espaço após o nome (no seu PDF há linhas com apenas 1 espaço entre nome e plano)
POLICY_RE = re.compile(
    r"""^\s*(?P<policy>\d{9,10}[A-Z]?)\s+                 # policy
    (?P<name>[A-Z0-9 .,'\-&/]+?)\s+                       # name (1+ espaço)
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

# ----------------------------
# Extração de texto com múltiplos fallbacks
# ----------------------------
def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """
    Extrai texto com múltiplos fallbacks:
    1) pdfplumber (pdfminer)
    2) PyMuPDF (fitz)
    3) PyPDF2
    Normaliza espaços ao final.
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

    # 2) PyMuPDF (fitz), se necessário
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

    # 3) PyPDF2, se ainda não vier nada útil
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

    # normalização final
    for ch in ["\u00A0", "\u2007", "\u202F"]:
        text = text.replace(ch, " ")
    text = text.replace("\t", "    ")
    return text

# ----------------------------
# Extrair data do relatório (do cabeçalho)
# ----------------------------
def extract_report_date_iso(text: str) -> Optional[str]:
    """
    Procura uma data tipo mm/dd/yy (ou yyyy) no cabeçalho, preferindo a linha
    que contém 'DAILY NEW BUSINESS/UNDERWRITING ACTIVITY REPORT'.
    Retorna ISO 'YYYY-MM-DD' ou None.
    """
    # 1) tentar nas primeiras linhas, junto da frase do relatório
    for line in text.splitlines()[:20]:
        m = re.search(
            r'(\d{1,2}/\d{1,2}/\d{2,4})\s+DAILY NEW BUSINESS/UNDERWRITING ACTIVITY REPORT',
            line, flags=re.IGNORECASE
        )
        if m:
            iso = _date_to_iso(m.group(1))
            if iso:
                return iso

    # 2) fallback: primeira data na primeira página (~primeiros 500 chars)
    m2 = re.search(r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b', text[:500])
    if m2:
        return _date_to_iso(m2.group(1))

    return None

def _date_to_iso(raw: str) -> Optional[str]:
    raw = raw.strip()
    # tenta mm/dd/yy e mm/dd/yyyy
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            dt = datetime.datetime.strptime(raw, fmt).date()
            return dt.isoformat()
        except Exception:
            pass
    return None

# ----------------------------
# Helpers do parser (colunas e tokens)
# ----------------------------
def _to_float_premium(s: str):
    try:
        return float(s.replace(",", ""))
    except Exception:
        return None

def _parse_policy_line_by_columns(line: str):
    """
    Fallback para tabelas com plano/prêmio:
    [policy, name, plan, premium, agent_id, agent]
    """
    parts = re.split(r"\s{2,}", line.strip())
    if len(parts) < 6:
        return None
    policy, name, plan, premium, agent_id, agent = parts[:6]
    if not re.match(r"^\d{9,10}[A-Z]?$", policy):
        return None
    if not re.match(r"^[A-Z0-9\-]+$", plan):
        return None
    if not re.match(r"^[\d,]+\.\d{2}$", premium):
        return None
    if not re.match(r"^\d{6,7}$", agent_id):
        return None
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
    """
    Fallback para blocos de UNDERWRITING REQUIREMENTS:
    [policy, name, requirement_desc, agent_id, agent]
    """
    parts = re.split(r"\s{2,}", line.strip())
    if len(parts) < 5:
        return None
    policy, name, requirement, agent_id, agent = parts[:5]
    if not re.match(r"^\d{9,10}[A-Z]?$", policy):
        return None
    if not re.match(r"^\d{6,7}$", agent_id):
        return None
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
    """
    Fallback por tokens (1+ espaços):
    policy | ...nome... | plan | premium | agent_id | ...agent name...
    """
    parts = re.split(r"\s+", line.strip())
    if len(parts) < 6:
        return None

    # policy = primeiro token
    policy = parts[0]
    if not re.match(r"^\d{9,10}[A-Z]?$", policy):
        return None

    # agent_id = último token que bate \d{6,7}
    try:
        agent_id_idx = max(i for i, t in enumerate(parts) if re.match(r"^\d{6,7}$", t))
    except ValueError:
        return None
    agent_id = parts[agent_id_idx]

    # premium = token imediatamente antes do agent_id
    if agent_id_idx - 1 < 0:
        return None
    premium = parts[agent_id_idx - 1]
    if not re.match(r"^[\d,]+\.\d{2}$", premium):
        return None

    # plan = token antes do premium
    if agent_id_idx - 2 < 0:
        return None
    plan = parts[agent_id_idx - 2]
    if not re.match(r"^[A-Z0-9\-]+$", plan):
        return None

    # name = tudo entre policy e plan
    name_tokens = parts[1:agent_id_idx - 2]
    if not name_tokens:
        return None
    name = " ".join(name_tokens)

    # agent = tudo após agent_id
    agent_tokens = parts[agent_id_idx + 1:]
    if not agent_tokens:
        return None
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

# ----------------------------
# Parser tolerante
# ----------------------------
def parse_report(text: str) -> List[Dict]:
    """
    Parser tolerante:
    - Detecta status por substring.
    - Usa regex OU fallbacks (colunas e tokens).
    - Se não houver header ainda, marca blocos plausíveis como 'UNKNOWN'.
    """
    out: List[Dict] = []
    status: Optional[str] = None

    def detect_status(line: str) -> Optional[str]:
        u = re.sub(r"\s+", " ", line).strip().upper()
        if not u:
            return None
        if "UNDERWRITING REQUIREMENTS" in u and "ADDED" in u:
            return "UNDERWRITING REQUIREMENTS ADDED"
        if "UNDERWRITING REQUIREMENTS" in u and "UPDATED" in u:
            return "UNDERWRITING REQUIREMENTS UPDATED"
        if "SUBMITTED" in u:
            return "SUBMITTED"
        if "ISSUED" in u:
            return "ISSUED"
        if "DELIVERED" in u:
            return "DELIVERED"
        if "DECLINE" in u or "DECLINED" in u:
            return "DECLINE"
        if "INCOMPLETE" in u:
            return "INCOMPLETE"
        if "WITHDRAWN" in u:
            return "WITHDRAWN"
        return None

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue

        # 1) troca de seção por status (tolerante)
        new_status = detect_status(line)
        if new_status:
            status = new_status
            continue

        # 2) blocos com plano/prêmio
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

            parsed = _parse_policy_line_by_tokens(line)  # fallback por tokens
            if parsed:
                parsed["status"] = status or "UNKNOWN"
                out.append(parsed)
                continue

        # 3) blocos de underwriting requirements
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

# ----------------------------
# Endpoints
# ----------------------------
@app.get("/")
def root():
    return {"ok": True, "service": "Underwriting Extractor - Local (robusto)"}

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/extract")
async def extract(
    pdf: UploadFile = File(...),
    forward_url: Optional[str] = Form(None),       # aceita vazio sem erro
    return_text_sample: Optional[str] = Form(None) # "1" para retornar amostra do texto
):
    if not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo .pdf")

    content: bytes = await pdf.read()
    text = extract_text_from_bytes(content)

    # NOVO: extrai a data do cabeçalho e converte para ISO
    report_date = extract_report_date_iso(text)

    data = parse_report(text)

    # Anexa a data em cada item (e também retornamos no topo)
    if report_date:
        for it in data:
            it["report_date"] = report_date

    forwarded = None
    if forward_url and forward_url.strip():
        try:
            r = requests.post(forward_url.strip(), json=data, timeout=30)
            forwarded = {"status_code": r.status_code, "body": r.text[:400]}
        except Exception as e:
            forwarded = {"error": str(e)}

    resp = {
        "count": len(data),
        "report_date": report_date,   # <--- no topo também
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
import datetime, re, requests
from typing import List, Dict, Optional
from fastapi import UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

# --- helpers de data ---
def _ret_date_iso(s: str) -> Optional[str]:
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass
    return None

def extract_return_report_date_iso(text: str) -> Optional[str]:
    # tenta uma linha que contenha "DAILY RETURN DRAFT"
    for line in text.splitlines()[:30]:
        if "DAILY RETURN DRAFT" in line.upper():
            m = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', line)
            if m:
                return _ret_date_iso(m.group(1))
    # fallback: primeira data no começo do arquivo
    m2 = re.search(r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b', text[:500])
    return _ret_date_iso(m2.group(1)) if m2 else None

# --- parser principal ---
REASON_START = {
    "NSF","RETURN","PAYMENT","NO","ACCT","ACCOUNT","CUSTOMER","CUST","NOT",
    "UNABLE","LOCATE","LOCAT","INVALID","REFER","STOPPED","CLOSED","CODE",
    "NUMBER","AUTH","R98"
}

def parse_return_items(text: str) -> Dict[str, List[Dict]]:
    """
    Retorna {"returned_items": [...], "returned_pre_notes": [...]}
    Cada item tem:
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

        # cabeçalho de página
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

        # detectar seção
        if "RETURNED ITEMS" in u:
            section = "RETURNED ITEMS"
            continue
        if "RETURNED PRE-NOTES" in u or "RETURNED PRE NOTES" in u:
            section = "RETURNED PRE-NOTES"
            continue

        # linha de item (começa com COM + POLICY)
        m = re.match(r'^\s*(\d{3})\s+(\d{10}[A-Z]?)\s+(.+)$', ln)
        if not m:
            continue

        company_code = m.group(1)
        policy_no = m.group(2)
        rest = m.group(3).strip()
        tokens = re.split(r'\s+', rest)
        if len(tokens) < 8:
            continue

        # localizar BILL DAY + ISSUE DATE (padrão: 2 dígitos + data)
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

        # separar agent_name x reason
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

# --- endpoint: usa a MESMA função extract_text_from_bytes do seu main.py ---
@app.post("/returns")
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

    # usa sua função já existente de extração de texto
    text = extract_text_from_bytes(content)  # <-- reaproveita a do main.py
    report_date = extract_return_report_date_iso(text)
    parsed = parse_return_items(text)

    # anexa report_date em cada item
    for lst in parsed.values():
        for it in lst:
            it["report_date"] = report_date

    # opcional: encaminhar
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
