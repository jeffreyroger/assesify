try:
    import PyPDF2
except Exception:
    PyPDF2 = None


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts text from a PDF file. If PyPDF2 is not installed, raise a clear error when called.
    """
    if PyPDF2 is None:
        raise RuntimeError("PyPDF2 is required to extract PDF text but is not installed in this environment.")

    text = ""
    with open(pdf_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            text += (page.extract_text() or "") + "\n"

    return text.strip()
