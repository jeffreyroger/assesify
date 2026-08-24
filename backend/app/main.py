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
from app.models.audit_log import AuditLog
from app.models.oauth_state import OAuthState
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
from app.api.v1.admin.routes import admin_bp

#: HTTP status -> (spec §4.5 error code, default human message).
ERROR_CODES = {
    400: ("VALIDATION_ERROR", "The request payload is invalid."),
    401: ("UNAUTHORIZED", "Authentication is required."),
    403: ("FORBIDDEN", "You do not have access to this resource."),
    404: ("NOT_FOUND", "Resource not found."),
    405: ("METHOD_NOT_ALLOWED", "That method is not allowed on this resource."),
    409: ("CONFLICT", "The request conflicts with the current state."),
    413: ("VALIDATION_ERROR", "The upload exceeds the 25 MB limit."),
    415: ("UNSUPPORTED_MEDIA_TYPE", "Unsupported media type."),
    422: ("VALIDATION_ERROR", "The request payload could not be processed."),
    429: ("RATE_LIMITED", "Too many requests; slow down."),
    500: ("INTERNAL_ERROR", "An unexpected error occurred."),
    502: ("BAD_GATEWAY", "An upstream service failed."),
    503: ("SERVICE_UNAVAILABLE", "The service is temporarily unavailable."),
}


def error_response(status: int, message: str | None = None, code: str | None = None, details: dict | None = None):
    """Build a spec §4.5 error body. `msg` is duplicated for legacy clients."""
    default_code, default_message = ERROR_CODES.get(status, ("INTERNAL_ERROR", "Request failed."))
    message = message or default_message
    return jsonify({
        "error": {"code": code or default_code, "message": message, "details": details or {}},
        "msg": message,
    }), status


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
    request_counts = {"requests_total": 0, "requests_errors_total": 0,
                      "request_duration_ms_total": 0.0, "by_status": {}}

    # Avoid SQLAlchemy expiring object attributes on commit so tests can access ids from detached instances
    app.config.setdefault('SQLALCHEMY_EXPIRE_ON_COMMIT', False)
    # Also set session options to keep attributes accessible after commit/close
    app.config.setdefault('SQLALCHEMY_SESSION_OPTIONS', {'expire_on_commit': False})

    @app.before_request
    def begin_request():
        request.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.started_at = time.perf_counter()

    @app.after_request
    def normalize_error_envelope(response):
        """Guarantee spec §4.5's `{"error": {code, message, details}}` shape.

        Handlers across the app historically returned `{"msg": "..."}` for
        failures, and the frontend reads that field. Rather than break those
        clients, every 4xx/5xx JSON response that lacks an `error` key is
        wrapped here: the legacy keys are preserved alongside the envelope, so
        the contract is uniform for new clients and unchanged for old ones.
        """
        if response.status_code < 400 or not response.is_json:
            return response
        try:
            payload = response.get_json(silent=True)
        except Exception:
            return response
        if not isinstance(payload, dict) or "error" in payload:
            return response
        message = (
            payload.get("msg")
            or payload.get("message")
            or payload.get("description")
            or ERROR_CODES.get(response.status_code, ("INTERNAL_ERROR", "Request failed."))[1]
        )
        code = ERROR_CODES.get(response.status_code, ("INTERNAL_ERROR", ""))[0]
        payload["error"] = {"code": code, "message": message, "details": {}}
        response.set_data(json.dumps(payload))
        return response

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
        request_counts["by_status"][str(response.status_code)] = (
            request_counts["by_status"].get(str(response.status_code), 0) + 1
        )
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
    app.register_blueprint(admin_bp, url_prefix="/api/v1/admin")

    # Spec §4.5: every HTTP error leaves the API in the standard envelope,
    # including the ones Flask/Werkzeug raise before a view runs.
    from werkzeug.exceptions import HTTPException

    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        status = e.code or 500
        # 413 keeps the spec's explicit size-cap wording rather than
        # Werkzeug's generic description.
        message = None if status == 413 else e.description
        return error_response(status, message)

    @app.errorhandler(Exception)
    def handle_unexpected_exception(e):
        app.logger.exception(json.dumps({
            "event": "unhandled_exception",
            "request_id": getattr(request, "request_id", None),
            "path": request.path,
        }))
        if app.debug or app.testing:
            # Never mask real stack traces during development or tests.
            raise e
        return error_response(500)

    @app.route("/metrics")
    def metrics():
        """Prometheus text-format exposition (spec §9)."""
        total = request_counts["requests_total"]
        lines = [
            "# HELP assesify_requests_total Total HTTP requests served.",
            "# TYPE assesify_requests_total counter",
            f"assesify_requests_total {total}",
            "# HELP assesify_request_errors_total HTTP requests answered with a 4xx/5xx status.",
            "# TYPE assesify_request_errors_total counter",
            f"assesify_request_errors_total {request_counts['requests_errors_total']}",
            "# HELP assesify_request_duration_ms_total Cumulative request handling time in milliseconds.",
            "# TYPE assesify_request_duration_ms_total counter",
            f"assesify_request_duration_ms_total {request_counts['request_duration_ms_total']}",
            "# HELP assesify_responses_by_status_total HTTP responses partitioned by status code.",
            "# TYPE assesify_responses_by_status_total counter",
        ]
        for status, count in sorted(request_counts["by_status"].items()):
            lines.append(f'assesify_responses_by_status_total{{status="{status}"}} {count}')
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
