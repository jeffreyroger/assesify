"""Create a student account for testing the Weekly Test feature."""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app
from app.models.users import db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    # Check if student already exists
    student = User.find_by_email('student@assesify.com')
    
    if student:
        print(f"✓ Student account already exists: {student.email}")
        print(f"  ID: {student.id}")
        print(f"  Name: {student.full_name}")
    else:
        # Create new student account
        student = User(
            email='student@assesify.com',
            full_name='Test Student',
            password_hash=generate_password_hash('password123'),
            is_teacher=False  # This is a student!
        )
        db.session.add(student)
        db.session.commit()
        
        print("✓ Created new student account!")
        print(f"  Email: student@assesify.com")
        print(f"  Password: password123")
        print(f"  ID: {student.id}")
        print(f"  Is Teacher: {student.is_teacher}")
    
    print("\n" + "="*60)
    print("LOGIN CREDENTIALS FOR STUDENT ACCOUNT:")
    print("="*60)
    print("Email: student@assesify.com")
    print("Password: password123")
    print("="*60)
