# app/models.py
from pydantic import BaseModel
from typing import Optional, Dict, List, Any

class ConfirmPayload(BaseModel):
    upload_token: str
    custom_data: Optional[Dict] = None
    forward_url: Optional[str] = None
    bearer: Optional[str] = None
    basic: Optional[str] = None

class FileMeta(BaseModel):
    name: str
    size_bytes: int
    size_mb: float
    content_type: str
    cached_at: Optional[str] = None

class UnderwritingItem(BaseModel):
    status: str
    policy_no: str
    insured_name: str
    plan: Optional[str] = None
    annual_premium: Optional[float] = None
    agent_id: str
    writing_agent: str
    requirement_desc: Optional[str] = None
    report_date: Optional[str] = None

class ReturnItem(BaseModel):
    section: Optional[str] = None
    company_code: str
    policy_no: str
    insured_name: str
    bill_day: str
    issue_date: Optional[str] = None
    bill_no: Optional[str] = None
    amount: Optional[float] = None
    agency_code_line: Optional[str] = None
    agent_num: Optional[str] = None
    agent_name: Optional[str] = None
    reason: Optional[str] = None
    page_region_code: Optional[str] = None
    page_region_desc: Optional[str] = None
    page_agency_code: Optional[str] = None
    page_agency_desc: Optional[str] = None
    report_date: Optional[str] = None

class ReturnItems(BaseModel):
    returned_items: List[ReturnItem]
    returned_pre_notes: List[ReturnItem]

class ComparisonSummary(BaseModel):
    new_file: str
    old_file: Optional[str] = None
    total_changes: int
    new_records: int
    modified_records: int

class ComparisonResult(BaseModel):
    comparison_summary: ComparisonSummary
    changes: List[Dict[str, Any]]

class ForwardResponse(BaseModel):
    status_code: Optional[int] = None
    body: Optional[str] = None
    error: Optional[str] = None

class UploadCache(BaseModel):
    filename: str
    content: bytes
    content_type: str
    cached_at: str
