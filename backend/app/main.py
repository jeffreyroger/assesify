import sys
import os
import json
import logging
import time
import uuid

# Add backend folder to sys.path so absolute imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env'))

from flask import Flask, request, jsonify
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from app.core.config import Config
from app.models.users import db
from app.models.submission import QuizAttempt, QuizAnswer
from app.api.v1.auth.routes import auth_bp
# teacher blueprint can import heavy ML deps; import optionally so quick dev runs don't fail
try:
    from app.api.v1.teacher.routes import teacher_bp
except Exception:
    teacher_bp = None
from app.api.v1.classes.routes import classes_bp
from app.api.v1.lessons.routes import lessons_bp
from app.api.v1.quizzes.routes import quizzes_bp
from app.api.v1.students.routes import students_bp
from app.api.v1.materials.routes import materials_bp
from app.api.v1.attempts.routes import attempts_bp
from app.api.v1.quiz_api.routes import quiz_api_bp
from app.api.v1.analytics_v1.routes import analytics_v1_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Enable CORS for API endpoints. For local dev allow any origin (no credentials).
    # In production set FRONTEND_URL to the frontend host and remove allow_headers or set supports_credentials=True appropriately.
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    if frontend_url:
        # Restrict CORS to the configured frontend and enable credentials (cookies) when set
        CORS(app, resources={r"/api/*": {"origins": frontend_url}}, supports_credentials=True)
    else:
        # Allow all origins for local development (no credentials)
        CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=False)

    # Fallback: ensure responses include CORS headers only for allowed origin
    request_counts = {"requests_total": 0, "requests_errors_total": 0, "request_duration_ms_total": 0.0}

    @app.before_request
    def begin_request():
        request.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.started_at = time.perf_counter()

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin")
        # Only reflect the configured frontend URL
        if origin and frontend_url and origin == frontend_url:
            response.headers["Access-Control-Allow-Origin"] = frontend_url
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
            response.headers["Access-Control-Allow-Credentials"] = "true"
        duration = (time.perf_counter() - getattr(request, "started_at", time.perf_counter())) * 1000
        request_counts["requests_total"] += 1
        request_counts["request_duration_ms_total"] += duration
        if response.status_code >= 400:
            request_counts["requests_errors_total"] += 1
        response.headers["X-Request-ID"] = request.request_id
        app.logger.info(json.dumps({"event": "request", "request_id": request.request_id,
                                   "method": request.method, "path": request.path,
                                   "status": response.status_code, "duration_ms": round(duration, 2)}))
        return response
        duration = (time.perf_counter() - getattr(request, "started_at", time.perf_counter())) * 1000
        request_counts["requests_total"] += 1
        request_counts["request_duration_ms_total"] += duration
        if response.status_code >= 400:
            request_counts["requests_errors_total"] += 1
        response.headers["X-Request-ID"] = request.request_id
        app.logger.info(json.dumps({"event": "request", "request_id": request.request_id,
                                   "method": request.method, "path": request.path,
                                   "status": response.status_code, "duration_ms": round(duration, 2)}))
        return response
    db.init_app(app)
    Migrate(app, db)
    jwt = JWTManager(app)

    # Register blocklist loader to prevent reuse of revoked refresh tokens
    from app.models.refresh_token import RefreshToken

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        try:
            jti = jwt_payload.get("jti")
            if not jti:
                return False
            row = RefreshToken.query.filter_by(jti=jti).first()
            # If token is present and revoked, block it. If absent, allow (access tokens may not be stored).
            return bool(row and row.revoked)
        except Exception:
            # On DB errors, default to not blocked so as not to break healthy flows
            app.logger.exception("Error checking token blocklist")
            return False

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    if teacher_bp:
        app.register_blueprint(teacher_bp, url_prefix="/api/teacher")
    app.register_blueprint(classes_bp, url_prefix="/api/classes")
    app.register_blueprint(lessons_bp, url_prefix="/api/lessons")
    app.register_blueprint(quizzes_bp, url_prefix="/api/quizzes")
    # The original /api routes remain for the existing UI; new clients use the
    # versioned contract described in SPEC.md.
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth", name="auth_v1")
    if teacher_bp:
        app.register_blueprint(teacher_bp, url_prefix="/api/v1/teacher", name="teacher_v1")
    app.register_blueprint(classes_bp, url_prefix="/api/v1/classes", name="classes_v1")
    app.register_blueprint(lessons_bp, url_prefix="/api/v1/lessons", name="lessons_v1")
    app.register_blueprint(quiz_api_bp, url_prefix="/api/v1/quizzes")
    app.register_blueprint(students_bp, url_prefix="/api/v1/students")
    app.register_blueprint(materials_bp, url_prefix="/api/v1/materials")
    app.register_blueprint(attempts_bp, url_prefix="/api/v1")
    app.register_blueprint(analytics_v1_bp, url_prefix="/api/v1")

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Resource not found.", "details": {}}}), 404

    @app.errorhandler(413)
    def file_too_large(_):
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "The upload exceeds the 25 MB limit.", "details": {}}}), 413

    @app.route("/metrics")
    def metrics():
        lines = ["# TYPE assesify_requests_total counter", f"assesify_requests_total {request_counts['requests_total']}",
                 "# TYPE assesify_request_errors_total counter", f"assesify_request_errors_total {request_counts['requests_errors_total']}",
                 "# TYPE assesify_request_duration_ms_total counter", f"assesify_request_duration_ms_total {request_counts['request_duration_ms_total']}"]
        return "\n".join(lines) + "\n", 200, {"Content-Type": "text/plain; version=0.0.4"}

    @app.route("/")
    def home():
        return {"message": "Assesify API is running"}

    # Debug route (local dev only) to inspect request headers
    @app.route("/_debug/headers", methods=["GET","POST","OPTIONS"])
    def debug_headers():
        from flask import jsonify
        headers = {k: v for k, v in request.headers.items()}
        return jsonify(headers)

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
