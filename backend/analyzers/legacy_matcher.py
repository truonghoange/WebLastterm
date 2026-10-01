"""Optional comparison adapter. Its old scores never drive the new pipeline."""
from matcher import calculate_match
from processor import process_data


def compare(cv_text: str, jd_text: str, industry: str = "Other") -> dict:
    cv_data, jd_data = process_data(cv_text, jd_text, industry)
    return calculate_match(cv_data, jd_data)
