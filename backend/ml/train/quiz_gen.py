# quiz_gen.py
from typing import List, Dict, Any, Optional
import re
import os
import time
import difflib

# AI interaction helpers (Gemini client)
from ml.genai import GeminiClient
from ml.schemas import StructuredAnswer, QuizItem

PROMPT_FILENAME = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts", "generate_mcq_v1.txt")


def _load_prompt_template() -> Optional[str]:
    """Load a versioned prompt template if available; otherwise None."""
    try:
        if os.path.exists(PROMPT_FILENAME):
            with open(PROMPT_FILENAME, "r", encoding="utf-8") as fh:
                return fh.read()
    except Exception:
        pass
    return None


def ai_generate_answer(question: str) -> str:
    """Generate a short textual answer for a question using the configured model.
    Falls back to a placeholder string if model is not configured or call fails.
    """
    try:
        client = GeminiClient()
        return client.generate_text(question)
    except Exception:
        return "Answer TBD"



def _try_structured_answer(question: str, difficulty: str = "medium", retries: int = 2) -> dict:
    """Ask the model to return a JSON object with 'answer', 'options' and 'hint'.

    Retries the model up to `retries` times when JSON parsing/validation fails.
    Uses a versioned prompt file when available.
    """
    prompt_template = _load_prompt_template()
    if prompt_template:
        prompt = prompt_template.replace("{{DIFFICULTY}}", difficulty).replace("{{QUESTION}}", question)
    else:
        prompt = (
            f"Please provide a JSON object representing a {difficulty}-level multiple choice question based on the text below. "
            "The object must have the following keys:\n"
            "- 'answer': A concise explanation of why the correct option is right.\n"
            "- 'options': A list of exactly 4 distinct options (strings). One must be correct, others plausible distractors.\n"
            "- 'correct_answer': The exact string content of the correct option from the list.\n"
            "- 'hint': A short hint.\n"
            "Return ONLY valid JSON.\n\n"
            f"Context/Question: {question}"
        )

    client = GeminiClient()
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return client.generate_json(prompt)
        except Exception as e:
            last_exc = e
            # small backoff
            time.sleep(0.2 * (attempt + 1))
            continue
    # if all retries failed, raise the last exception
    if last_exc:
        raise last_exc
    raise ValueError("Unknown error in structured answer generation")


def chunk_text(text: str, max_words: int = 1200, overlap: int = 150) -> List[str]:
    """Split text into semantic-like chunks using word windows with overlap.

    Default sizes match the spec (1200 words, 150 overlap). When the text is short,
    this will return a single chunk.
    """
    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [" ".join(words)]

    chunks: List[str] = []
    start = 0
    step = max_words - overlap if max_words > overlap else max_words
    while start < len(words):
        chunk_words = words[start:start + max_words]
        chunks.append(" ".join(chunk_words))
        if start + max_words >= len(words):
            break
        start += step
    return chunks


def _excerpt_for_question(text: str, max_chars: int = 120) -> str:
    """Return a clean excerpt suitable for embedding in a question."""
    s = " ".join(text.split())
    # fix common ligatures and stick abbreviations
    s = s.replace('\ufb01', 'fi')
    s = re.sub(r'([A-Z]{2,})([A-Z][a-z])', r'\1 \2', s)

    # split into sentences using basic punctuation
    sentences = re.split(r'(?<=[.!?])\s+', s)

    # Prefer a complete first sentence; if too short, join first two sentences
    if sentences and len(sentences[0]) >= 40:
        excerpt = sentences[0].strip()
    elif len(sentences) >= 2:
        excerpt = (sentences[0] + ' ' + sentences[1]).strip()
    else:
        if len(s) <= max_chars:
            excerpt = s
        else:
            truncated = s[:max_chars]
            excerpt = truncated.rsplit(' ', 1)[0].strip()

    # remove final sentence punctuation
    excerpt = excerpt.rstrip(' ,;:')
    if excerpt and excerpt[-1] in '.!?':
        excerpt = excerpt[:-1].strip()

    return excerpt


def validate_and_dedupe(items: List[Dict[str, Any]], similarity_threshold: float = 0.92) -> List[Dict[str, Any]]:
    """Validate each generated item with Pydantic and remove near-duplicates.

    Embedding-based deduplication is preferred per spec, but when an embedding
    service is not available this function falls back to a text-similarity
    approach (difflib.SequenceMatcher) which approximates semantic overlap.
    Returns a filtered list preserving original order.
    """
    validated: List[Dict[str, Any]] = []
    texts: List[str] = []
    for raw in items:
        # try pydantic validation
        try:
            sa = StructuredAnswer(**{
                "answer": raw.get("answer") or raw.get("explanation") or "",
                "options": raw.get("options") or [],
                "correct_answer": raw.get("correct_answer") or raw.get("correct_keys") or "",
                "hint": raw.get("hint") or raw.get("explanation") or None,
            })
        except Exception:
            # skip invalid items
            continue
        qtext = str(raw.get("question") or raw.get("stem") or "").strip()
        # dedupe using text similarity
        is_dup = False
        for existing in texts:
            sim = difflib.SequenceMatcher(a=existing.lower(), b=qtext.lower()).ratio()
            if sim >= similarity_threshold:
                is_dup = True
                break
        if not is_dup:
            texts.append(qtext)
            validated.append({
                "question": qtext,
                "answer": sa.answer,
                "options": sa.options,
                "correct_answer": sa.correct_answer,
                "hint": sa.hint,
            })
    return validated


def generate_quiz(chunk: str, difficulty: str = "medium") -> List[Dict[str, Any]]:
    """Generate a quiz from a chunk of text.
    Returns a list of dicts: {'question', 'answer', 'options', 'correct_answer', 'hint'}

    Uses structured JSON generation when possible; retries the model up to two times
    before falling back to a simple rule-based generator.
    """
    excerpt = _excerpt_for_question(chunk)
    question_text = f'What is the main idea of the following passage: "{excerpt}"?'

    generated: List[Dict[str, Any]] = []

    # Try to get a structured JSON from the model (with retries)
    try:
        resp = _try_structured_answer(question_text, difficulty=difficulty, retries=2)
        if isinstance(resp, dict):
            # If the model returned a single question object
            try:
                sa = StructuredAnswer(**resp)
                generated.append({
                    "question": question_text,
                    "answer": sa.answer,
                    "options": sa.options,
                    "correct_answer": sa.correct_answer,
                    "hint": sa.hint,
                })
            except Exception:
                # Schema validation failed — tolerate partial outputs by using available keys
                answer_val = resp.get("answer") or resp.get("explanation") or "Answer TBD"
                options_val = resp.get("options") or [answer_val, "An alternate idea", "A common misconception", "Irrelevant fact"]
                correct_val = resp.get("correct_answer") or (options_val[0] if options_val else answer_val)
                hint_val = resp.get("hint") or resp.get("explanation") or "Summarize the passage."
                generated.append({
                    "question": question_text,
                    "answer": answer_val,
                    "options": options_val,
                    "correct_answer": correct_val,
                    "hint": hint_val,
                })

    except Exception:
        # model failed repeatedly; fall back
        pass

    # Fallback rule-based generation if no valid structured output
    if not generated:
        # Simple approach: produce a generic MCQ with placeholder options and try to call the text generator for an answer
        try:
            answer_text = ai_generate_answer(question_text)
        except Exception:
            answer_text = "Answer TBD"
        options = [f"{answer_text}", "An alternate idea", "A common misconception", "Irrelevant fact"]
        generated.append({
            "question": question_text,
            "answer": answer_text,
            "options": options,
            "correct_answer": options[0],
            "hint": "Summarize the passage in one sentence.",
        })

    # Validate and dedupe before returning
    final = validate_and_dedupe(generated)
    return final
