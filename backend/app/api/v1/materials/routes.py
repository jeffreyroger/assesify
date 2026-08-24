import mimetypes
import os
import time

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.utils import secure_filename

from app.models.assessment import Material, Question
from app.models.lesson import Lesson
from app.models.quiz import Quiz
from app.models.users import User, db
from ml.train.quiz_gen import chunk_text, generate_quiz
from ml.utils.pdf_utils import extract_text_from_pdf
from ml.utils.text_cleaner import clean_text

materials_bp = Blueprint("materials", __name__)
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
MAX_FILE_SIZE = 25 * 1024 * 1024


def _error(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message, "details": {}}}), status


def _extract(path, extension):
    if extension == "pdf":
        return extract_text_from_pdf(path)
    if extension == "docx":
        from docx import Document
        return "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
    with open(path, encoding="utf-8") as source:
        return source.read()


@materials_bp.route("", methods=["POST"])
@jwt_required()
def create_material():
    user = User.query.get(int(get_jwt_identity()))
    if not user or not user.is_teacher:
        return _error("FORBIDDEN", "Only teachers can upload materials.", 403)
    file = request.files.get("file")
    if not file or not file.filename:
        return _error("VALIDATION_ERROR", "file is required")
    filename = secure_filename(file.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        return _error("VALIDATION_ERROR", "Only PDF, DOCX, and TXT files are supported.")
    file.seek(0, os.SEEK_END)
    if file.tell() > MAX_FILE_SIZE:
        return _error("VALIDATION_ERROR", "The upload exceeds the 25 MB limit.")
    file.seek(0)
    upload_dir = os.path.join(os.path.dirname(current_app.root_path), "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    saved_name = f"{user.id}_{int(time.time())}_{filename}"
    saved_path = os.path.join(upload_dir, saved_name)
    file.save(saved_path)
    try:
        extracted = clean_text(_extract(saved_path, extension))
    except Exception as exc:
        return _error("EXTRACTION_ERROR", f"Could not extract text: {exc}", 422)
    if not extracted:
        return _error("EXTRACTION_ERROR", "No readable text was found in the uploaded file.", 422)
    material = Material(owner_id=user.id, title=request.form.get("title") or filename,
                        file_path=saved_name, mime_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
                        extracted_text=extracted)
    db.session.add(material)
    db.session.commit()
    return jsonify(material.to_dict()), 201


@materials_bp.route("/<int:material_id>", methods=["GET"])
@jwt_required()
def get_material(material_id):
    material = Material.query.get_or_404(material_id)
    if int(get_jwt_identity()) != material.owner_id:
        return _error("FORBIDDEN", "You do not own this material.", 403)
    return jsonify(material.to_dict(include_text=True))


@materials_bp.route("/<int:material_id>/generate-quiz", methods=["POST"])
@jwt_required()
def generate_material_quiz(material_id):
    material = Material.query.get_or_404(material_id)
    if int(get_jwt_identity()) != material.owner_id:
        return _error("FORBIDDEN", "You do not own this material.", 403)
    payload = request.get_json(silent=True) or {}
    count = max(1, min(int(payload.get("num_questions", 10)), 50))
    difficulty_name = payload.get("difficulty", "mixed")
    difficulty = "medium" if difficulty_name == "mixed" else difficulty_name
    tags = payload.get("competency_tags") or ["general"]
    questions = []
    for chunk in chunk_text(material.extracted_text, max_words=180):
        questions.extend(generate_quiz(chunk, difficulty=difficulty))
        if len(questions) >= count:
            break
    if not questions:
        return _error("GENERATION_ERROR", "Question generation did not produce any questions.", 502)
    lesson = Lesson(title=material.title, content=material.extracted_text, topic=tags[0],
                    file_path=material.file_path, teacher_id=material.owner_id)
    db.session.add(lesson)
    db.session.flush()
    quiz = Quiz(lesson_id=lesson.id, questions=questions[:count])
    db.session.add(quiz)
    db.session.flush()
    for item in questions[:count]:
        options = item.get("options", [])
        correct = item.get("correct_answer")
        option_rows = [{"key": chr(65 + i), "text": value} for i, value in enumerate(options)]
        correct_keys = [row["key"] for row in option_rows if row["text"] == correct]
        db.session.add(Question(quiz_id=quiz.id, stem=item.get("question", ""), qtype="mcq",
                                options=option_rows, correct_keys=correct_keys or ["A"],
                                explanation=item.get("answer"), difficulty={"easy": .3, "medium": .5, "hard": .8}.get(difficulty, .5),
                                competency_tag=tags[0]))
    db.session.commit()
    return jsonify({"id": quiz.id, "material_id": material.id, "title": material.title,
                    "num_questions": len(questions[:count]), "competency_tags": tags}), 201
