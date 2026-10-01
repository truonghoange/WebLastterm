"""Compatibility adapter for the old (text, error) upload contract."""
from backend.exceptions import DocumentParseError
from backend.parsers.file_parser import FileParser

def extract_text_from_upload(uploaded_file):
    if uploaded_file is None:
        return "", None
    try:
        return FileParser().parse(uploaded_file).raw_text, None
    except DocumentParseError as error:
        return "", f"{error.code}: {error}"
