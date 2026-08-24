import os
from typing import Tuple

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
MAX_FILE_SIZE = 25 * 1024 * 1024


def _has_pdf_magic(data: bytes) -> bool:
    return data.startswith(b"%PDF")


def _has_zip_magic(data: bytes) -> bool:
    return data.startswith(b"PK\x03\x04")


def validate_upload_stream(filename: str, stream) -> Tuple[bool, str]:
    """Validate uploaded file-like object. Returns (ok, message).

    Checks extension, size (stream must support seek/tell), and basic magic bytes.
    """
    if not filename or '.' not in filename:
        return False, "Invalid filename"
    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, "Unsupported file type"

    # check size
    try:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(0)
        if size > MAX_FILE_SIZE:
            return False, "File too large"
    except Exception:
        # can't determine size; be conservative
        return False, "Could not determine file size"

    # read header bytes
    header = stream.read(8)
    stream.seek(0)
    if ext == 'pdf':
        if not _has_pdf_magic(header):
            return False, "File content mismatch: not a valid PDF"
    elif ext == 'docx':
        if not _has_zip_magic(header):
            return False, "File content mismatch: not a valid DOCX (zip)"
    elif ext == 'txt':
        # ensure it's decodable as UTF-8 (try small sample)
        sample = stream.read(2048)
        stream.seek(0)
        try:
            sample.decode('utf-8') if isinstance(sample, bytes) else str(sample)
        except Exception:
            return False, "Text file not UTF-8 encoded"
    return True, "OK"
