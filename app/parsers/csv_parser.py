# app/parsers/csv_parser.py
import re
import io
import csv
from typing import List, Dict, Optional
from fastapi import HTTPException
from ..config import CSV_COMPARISON_FIELDS, NUMERIC_FIELDS, POLICY_COLUMN_CANDIDATES
from ..utils.helpers import is_valid_policy_number

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

def detect_policy_column(rows: List[Dict]) -> Optional[str]:
    """
    Automatically detects which column contains policy numbers.
    Returns the column name or None if not found.
    """
    if not rows:
        return None
    
    # List of candidates in priority order
    candidates = POLICY_COLUMN_CANDIDATES.copy()
    
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

def clean_and_normalize_row_with_policy_column(row: dict, policy_column: str) -> Optional[dict]:
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

def parse_csv_robust(content: str) -> List[Dict]:
    """
    Robust CSV parsing: tries direct parser; if it detects data fell only in the 1st column,
    normalizes by removing external quotes and unfolding internal quotes, then parses again.
    Then, detects the policy column and normalizes the rows.
    """
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

def compare_files_as_json_sync(new_content_str: str, old_file_meta: dict, new_filename: str) -> dict:
    """
    Synchronous comparison (for BackgroundTasks).
    """
    import requests
    
    try:
        old_file_url = old_file_meta.get('file', {}).get('url')
        if not old_file_url:
            raise ValueError("Old file URL not found in metadata.")
        r_old = requests.get(old_file_url, timeout=20)
        r_old.raise_for_status()
        old_content_str = r_old.content.decode('utf-8', errors='replace')

        list_new = parse_csv_robust(new_content_str)
        list_old = parse_csv_robust(old_content_str)

        if not list_new or 'Policy' not in list_new[0]:
            return {"error": "'Policy' column not found in the new file."}
        if not list_old or 'Policy' not in list_old[0]:
            return {"error": "'Policy' column not found in the old file."}

        map_new = {row['Policy']: row for row in list_new if row and row.get('Policy')}
        map_old = {row['Policy']: row for row in list_old if row and row.get('Policy')}

        keys_new = set(map_new.keys())
        keys_old = set(map_old.keys())

        added_ids = keys_new - keys_old
        added_policies = [map_new[pid] for pid in added_ids]

        common_ids = keys_new.intersection(keys_old)
        modified_policies = []

        for pid in common_ids:
            old_row = map_old[pid]; new_row = map_new[pid]
            has_changes = False
            for field in CSV_COMPARISON_FIELDS:
                old_value = old_row.get(field, '')
                new_value = new_row.get(field, '')
                old_norm = str(old_value).strip().lower() if old_value is not None else ''
                new_norm = str(new_value).strip().lower() if new_value is not None else ''
                if field in NUMERIC_FIELDS:
                    try:
                        old_num = float(old_norm.replace(',', '')) if old_norm else 0
                        new_num = float(new_norm.replace(',', '')) if new_norm else 0
                        if abs(old_num - new_num) > 0.01:
                            has_changes = True
                    except (ValueError, AttributeError):
                        if old_norm != new_norm:
                            has_changes = True
                else:
                    if old_norm != new_norm:
                        has_changes = True
            if has_changes:
                modified_policies.append(new_row)

        all_changes = []
        all_changes.extend(added_policies)
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
        return {"error": f"Error during JSON data comparison: {type(e).__name__} - {e}"}
