# app/parsers/returns_parser.py
import re
import datetime
from typing import Optional, Dict, List
from ..config import REASON_START
from ..utils.helpers import date_to_iso

def extract_return_report_date_iso(text: str) -> Optional[str]:
    """Extract report date from returns text"""
    for line in text.splitlines()[:30]:
        if "DAILY RETURN DRAFT" in line.upper():
            m = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', line)
            if m:
                return date_to_iso(m.group(1))
    m2 = re.search(r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b', text[:500])
    return date_to_iso(m2.group(1)) if m2 else None

def parse_return_items(text: str) -> Dict[str, List[Dict]]:
    """Parse return items from text and return organized data"""
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
        issue_date = date_to_iso(tokens[idx + 1])
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
