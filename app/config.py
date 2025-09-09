# app/config.py
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Destination (Bubble) and authentication
BUBBLE_URL: Optional[str] = os.getenv("BUBBLE_URL")
BUBBLE_TOKEN: Optional[str] = os.getenv("BUBBLE_TOKEN")

# Back4App Credentials
X_PARSE_APPLICATION_ID: str = os.getenv("X_PARSE_APPLICATION_ID", "tETk6wll2qxSh2OXxBWaLDh9ZjyGEvI9VppCVOe7")
X_PARSE_MASTER_KEY: str = os.getenv("X_PARSE_MASTER_KEY", "hAXjwSLgl7c2XlvL9gaPEhPcZbfbWvQ54um0EiOG")

# Back4app URLs
BACK4APP_FILES_URL: str = os.getenv("BACK4APP_FILES_URL", "https://parseapi.back4app.com/files")
BACK4APP_CSV_CLASS_URL: str = os.getenv("BACK4APP_CSV_CLASS_URL", "https://parseapi.back4app.com/classes/Csv")

# Upload limit (MB)
MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "20"))  # default 20 MB

# Default bearer token
DEFAULT_BEARER: str = "unitrust-7ccc52a2-d463-40ca-a414-23601eb28c80"

# Status headers for underwriting parser
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

# Reason start keywords for returns parser
REASON_START = {
    "NSF", "RETURN", "PAYMENT", "NO", "ACCT", "ACCOUNT", "CUSTOMER", "CUST", "NOT",
    "UNABLE", "LOCATE", "LOCAT", "INVALID", "REFER", "STOPPED", "CLOSED", "CODE",
    "NUMBER", "AUTH", "R98"
}

# Fields to check for changes in CSV comparison
CSV_COMPARISON_FIELDS = [
    'WritingAgent', 'AgentName', 'Company', 'Status', 'DOB', 'PolicyDate',
    'PaidtoDate', 'RecvDate', 'LastName', 'FirstName', 'MI', 'Plan', 'Face',
    'Form', 'Mode', 'ModePrem', 'Address1', 'Address2', 'Address3', 'Address4',
    'State', 'Zip', 'Phone', 'Email', 'App Date', 'WrtPct'
]

# Numeric fields for CSV comparison
NUMERIC_FIELDS = ['Face', 'ModePrem', 'WrtPct']

# Policy column candidates for CSV parsing
POLICY_COLUMN_CANDIDATES = [
    'Policy', 'Company', 'PolicyNumber', 'PolicyNo', 'Policy_Number', 'POLICY', 'COMPANY'
]
