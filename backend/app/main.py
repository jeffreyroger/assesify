import sys
import os

# Add backend folder to sys.path so absolute imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env'))

from flask import Flask, request
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

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Enable CORS for API endpoints. For local dev allow any origin (no credentials).
    # In production set FRONTEND_URL to the frontend host and remove allow_headers or set supports_credentials=True appropriately.
    frontend_url = os.environ.get("FRONTEND_URL")
    if frontend_url:
        CORS(app, resources={r"/api/*": {"origins": frontend_url}}, supports_credentials=True)
    else:
        # Allow all origins for local development (no credentials)
        CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=False)  # Enable CORS for API routes

    # Fallback: ensure responses include CORS headers for local dev frontend origins
    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin")
        if origin:
            # If FRONTEND_URL is set, only allow that origin. Otherwise allow the requesting origin.
            allowed = frontend_url if frontend_url else origin
            response.headers["Access-Control-Allow-Origin"] = allowed
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
            # Don't enable credentials for wildcard local dev
            if frontend_url:
                response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
    db.init_app(app)
    Migrate(app, db)
    JWTManager(app)

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    if teacher_bp:
        app.register_blueprint(teacher_bp, url_prefix="/api/teacher")
    app.register_blueprint(classes_bp, url_prefix="/api/classes")
    app.register_blueprint(lessons_bp, url_prefix="/api/lessons")
    app.register_blueprint(quizzes_bp, url_prefix="/api/quizzes")

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
