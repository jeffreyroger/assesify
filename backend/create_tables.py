from app.main import create_app
from app.models.users import db

app = create_app()
with app.app_context():
    db.create_all()
    print("Created tables via SQLAlchemy create_all()")
