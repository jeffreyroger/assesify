from flask import Blueprint, request, jsonify
from app.models.users import db
from app.models.lesson import Lesson
from app.models.quiz import Quiz
from ml.train.quiz_gen import generate_quiz, chunk_text
from ml.utils.text_cleaner import clean_text
from app.services.quiz_generation import persist_quiz_questions

lessons_bp = Blueprint('lessons', __name__)

@lessons_bp.route('/', methods=['POST'])
def create_lesson():
    data = request.get_json()
    title = data.get('title')
    content = data.get('content')
    topic = data.get('topic')
    class_id = data.get('class_id')

    if not title or not content:
        return jsonify({"error": "Title and content are required"}), 400

    new_lesson = Lesson(title=title, content=content, topic=topic, class_id=class_id)
    db.session.add(new_lesson)
    db.session.commit()

    return jsonify(new_lesson.to_dict()), 201

@lessons_bp.route('/', methods=['GET'])
def get_all_lessons():
    lessons = Lesson.query.order_by(Lesson.created_at.desc()).all()
    return jsonify([l.to_dict() for l in lessons])

@lessons_bp.route('/<int:lesson_id>', methods=['GET'])
def get_lesson(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    return jsonify(lesson.to_dict())

@lessons_bp.route('/<int:lesson_id>/quiz', methods=['POST'])
def generate_lesson_quiz(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    
    # 1. Prepare text
    cleaned_content = clean_text(lesson.content)
    chunks = chunk_text(cleaned_content, max_words=100) # Ensure chunks aren't too big

    # 2. Generate quiz
    full_quiz_data = []
    
    # Limit chunks to avoid excessive API calls if content is huge
    max_chunks = 5
    for i, chunk in enumerate(chunks[:max_chunks]):
        questions = generate_quiz(chunk)
        full_quiz_data.extend(questions)

    if not full_quiz_data:
        return jsonify({"error": "Failed to generate quiz questions"}), 500

    # 3. Save to DB (relational path — see app.services.quiz_generation)
    new_quiz = Quiz(lesson_id=lesson.id, questions=[])
    db.session.add(new_quiz)
    db.session.flush()
    persist_quiz_questions(new_quiz.id, full_quiz_data, competency_tag=lesson.topic or "general")
    db.session.commit()

    return jsonify(new_quiz.to_dict()), 201

@lessons_bp.route('/<int:lesson_id>/file', methods=['GET'])
def get_lesson_file(lesson_id):
    from flask import send_from_directory, current_app
    import os
    
    lesson = Lesson.query.get_or_404(lesson_id)
    if not lesson.file_path:
        return jsonify({"msg": "No file associated with this lesson"}), 404
        
    project_root = os.path.abspath(os.path.join(current_app.root_path, ".."))
    uploads_dir = os.path.join(project_root, "uploads")
    
    return send_from_directory(uploads_dir, lesson.file_path)
