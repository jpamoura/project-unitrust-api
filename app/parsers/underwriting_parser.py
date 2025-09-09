# app/parsers/underwriting_parser.py
import re
import datetime
from typing import Optional, List, Dict
from ..config import STATUS_HEADERS
from ..utils.helpers import date_to_iso, to_float_premium

# Regex patterns for underwriting parsing
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
            iso = date_to_iso(m.group(1))
            if iso:
                return iso
    m2 = re.search(r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b', text[:500])
    if m2:
        return date_to_iso(m2.group(1))
    return None

def _parse_policy_line_by_columns(line: str) -> Optional[Dict]:
    """Parse policy line by splitting on multiple spaces"""
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
        "annual_premium": to_float_premium(premium),
        "agent_id": agent_id,
        "writing_agent": agent.title(),
        "requirement_desc": None,
    }

def _parse_uw_line_by_columns(line: str) -> Optional[Dict]:
    """Parse underwriting requirement line by splitting on multiple spaces"""
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

def _parse_policy_line_by_tokens(line: str) -> Optional[Dict]:
    """Parse policy line by splitting on single spaces and finding agent_id"""
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
        "annual_premium": to_float_premium(premium),
        "agent_id": agent_id,
        "writing_agent": agent.title(),
        "requirement_desc": None,
    }

def parse_report(text: str) -> List[Dict]:
    """Parse underwriting report text and return list of policy items"""
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
                    "annual_premium": to_float_premium(d["premium"]),
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
