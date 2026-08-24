from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from pydantic import ValidationError
from app.models.users import db, User
from app.schemas.teacher import InviteStudentSchema
from app.models.lesson import Lesson
from app.models.quiz import Quiz
from werkzeug.utils import secure_filename
from app.core.authz import require_role
import os
import time

from ml.utils.pdf_utils import extract_text_from_pdf
from ml.utils.text_cleaner import clean_text
from ml.train.quiz_gen import chunk_text, generate_quiz

ALLOWED_EXTENSIONS = {"pdf", "txt", "docx"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB, per v1 specification

teacher_bp = Blueprint("teacher", __name__)

@teacher_bp.route("/ping", methods=["GET"])
def ping_teacher():
    return jsonify({"msg": "Teacher API is working"}), 200

@teacher_bp.route("/analytics", methods=["GET"])
@jwt_required()
@require_role('teacher')
def get_analytics():
    try:
        current_identity = get_jwt_identity()
        current_user_id = int(current_identity)
        teacher = User.query.get(current_user_id)

        # Fetch lessons created by this teacher
        lessons = Lesson.query.filter_by(teacher_id=current_user_id).all()
        
        analytics_data = []

        for lesson in lessons:
            from app.models.submission import QuizAttempt
            for quiz in lesson.quizzes:
                attempts = QuizAttempt.query.filter_by(quiz_id=quiz.id).all()
                
                quiz_results = {
                    "quiz_id": quiz.id,
                    "lesson_title": lesson.title,
                    "lesson_id": lesson.id,
                    "topic": lesson.topic,
                    "attempts_count": len(attempts),
                    "students": []
                }
                
                for att in attempts:
                    quiz_results["students"].append({
                        "student_name": att.user.full_name,
                        "student_email": att.user.email,
                        "score": att.score,
                        "completed_at": att.completed_at.isoformat() if att.completed_at else None,
                        "details": [a.to_dict() for a in att.answers]
                    })
                
                analytics_data.append(quiz_results)
    
        return jsonify(analytics_data), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500

@teacher_bp.route("/invite", methods=["POST"])
@jwt_required()
@require_role('teacher')
def invite_student():
    current_user_id = int(get_jwt_identity())
    # teacher identity already enforced by decorator

    try:
        data = InviteStudentSchema(**request.json)
    except ValidationError as e:
        return jsonify(e.errors()), 400

    if User.query.filter_by(email=data.email).first():
        return jsonify({"msg": "Student already exists"}), 400

    student = User(
        email=data.email,
        full_name=data.full_name,
        is_teacher=False
    )
    student.set_password("TempPassword123!")  # temp password
    db.session.add(student)
    db.session.commit()

    # TODO: send email with login link + temp password

    return jsonify({"msg": f"Student {data.full_name} invited successfully"}), 201


@teacher_bp.route("/materials", methods=["POST"])
@jwt_required()
@require_role('teacher')
def upload_material():
    # Note: this endpoint accepts uploads and processes them synchronously for now
    try:
        current_user_id = get_jwt_identity()
        teacher = User.query.get(int(current_user_id)) if current_user_id else None

        if "file" not in request.files:
            return jsonify({"msg": "file is required"}), 400

        file = request.files["file"]
        filename = secure_filename(file.filename or "")
        if not filename or "." not in filename:
            return jsonify({"msg": "Invalid filename"}), 400

        ext = filename.rsplit(".", 1)[1].lower()
        from app.core.uploads import validate_upload_stream
        ok, msg = validate_upload_stream(filename, file.stream)
        if not ok:
            return jsonify({"msg": msg}), 400

        # Save file to backend/uploads
        project_root = os.path.abspath(os.path.join(current_app.root_path, ".."))
        uploads_dir = os.path.join(project_root, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)

        timestamp = int(time.time())
        saved_name = f"{(teacher.id if teacher else 'anon')}_{timestamp}_{filename}"
        saved_path = os.path.join(uploads_dir, saved_name)
        file.save(saved_path)

        # Extract text based on extension
        try:
            if ext == "pdf":
                text = extract_text_from_pdf(saved_path)
            elif ext == "txt":
                with open(saved_path, "r", encoding="utf-8") as fh:
                    text = fh.read()
            elif ext == "docx":
                try:
                    from docx import Document
                    doc = Document(saved_path)
                    text = "\n".join(p.text for p in doc.paragraphs)
                except Exception:
                    return jsonify({"msg": "Could not read DOCX file (missing dependency)"}), 400
            else:
                text = ""
        except Exception as e:
            return jsonify({"msg": f"Failed to extract text: {e}"}), 500

        # Clean and chunk
        cleaned = clean_text(text)
        num_questions = int(request.form.get("numQuestions", request.form.get("num_questions", 10)))
        difficulty = request.form.get("difficulty", "medium")
        title = request.form.get("title", f"Quiz - {filename}")
        subject = request.form.get("subject", "Uploaded Material") # New parameter
        
        # Chunk text to ensure we have enough context for Qs
        # Adjust chunk size if we want more complex questions? 50 words is quite small. 
        chunks = chunk_text(cleaned, max_words=150) # Increased context for better Qs
        
        # Generate quiz items up to num_questions
        quiz_questions = []
        # If chunks < num_questions, we might run out. We could loop or use overlapping chunks.
        # For now, just generate as many as we can from chunks.
        for c in chunks:
            if len(c) < 50: continue # skip very short chunks
            generated = generate_quiz(c, difficulty=difficulty)
            quiz_questions.extend(generated)
            if len(quiz_questions) >= num_questions:
                break
                
        quiz_questions = quiz_questions[:num_questions]
        
        # SAVE TO DATABASE
        # 1. Create Lesson
        lesson = Lesson(
            title=title,
            content=cleaned, # Storing full text as lesson content
            topic=subject,
            file_path=saved_name,
            class_id=None, # Optionally link to class if we had class_id in form
            teacher_id=teacher.id if teacher else None
        )
        db.session.add(lesson)
        db.session.commit()
        
        # 2. Create Quiz
        quiz = Quiz(
            lesson_id=lesson.id,
            questions=quiz_questions
        )
        db.session.add(quiz)
        db.session.commit()

        return jsonify({
            "message": "Quiz generated and saved successfully",
            "quiz_id": quiz.id, 
            "lesson_id": lesson.id,
            "title": lesson.title, 
            "num_questions": len(quiz_questions)
        }), 201

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500
