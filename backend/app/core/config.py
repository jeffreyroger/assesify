import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "SUPER_SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:password123@localhost:5433/mydb"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "JWT_SUPER_SECRET")
    JWT_TOKEN_LOCATION = ["headers"]
