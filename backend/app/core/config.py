import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "SUPER_SECRET_KEY")
    # SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///assesify.db")
    SQLALCHEMY_DATABASE_URI = "sqlite:///assesify.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "JWT_SUPER_SECRET")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAALpHF3WID0SwotxGpEt0G9PeDBdjc0gY")
