from app.core.security import hash_password, verify_password
from app.core.uploads import validate_upload_stream
from io import BytesIO
import tempfile


def test_password_hash_and_verify():
    pwd = "correcthorsebatterystaple"
    h = hash_password(pwd)
    assert isinstance(h, str)
    assert verify_password(pwd, h) is True
    assert verify_password("wrong", h) is False


def test_validate_upload_pdf():
    # Create fake PDF header
    b = BytesIO(b"%PDF-1.4\n%...rest")
    ok, msg = validate_upload_stream("file.pdf", b)
    assert ok

def test_validate_upload_docx():
    b = BytesIO(b"PK\x03\x04" + b"whatever")
    ok, msg = validate_upload_stream("doc.docx", b)
    assert ok

def test_validate_upload_txt_non_utf8():
    # Create bytes that are invalid UTF-8
    b = BytesIO(bytes([0xff, 0xff, 0xff, 0xff]))
    ok, msg = validate_upload_stream("notes.txt", b)
    assert not ok
