from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.users import db, User
from app.models.classes import Class

classes_bp = Blueprint("classes", __name__)

@classes_bp.route("/", methods=["GET"])
@jwt_required()
def get_classes():
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    
    if not user:
        return jsonify({"msg": "User not found"}), 404

    classes_data = []
    seen_ids = set()
    
    # Add enrolled classes
    for cls in user.enrolled_classes:
        if cls.id not in seen_ids:
            classes_data.append({
                "id": cls.id,
                "name": cls.name,
                "section": cls.section,
                "teacher": cls.teacher.full_name,
                "code": cls.code,
                "progress": 0, 
                "color": "bg-brand-blue"
            })
            seen_ids.add(cls.id)

    # Add taught classes if user is a teacher
    if user.is_teacher:
        for cls in user.taught_classes:
            if cls.id not in seen_ids:
                classes_data.append({
                    "id": cls.id,
                    "name": cls.name,
                    "section": cls.section,
                    "teacher": user.full_name,
                    "code": cls.code,
                    "progress": 0,
                    "color": "bg-brand-purple"
                })
                seen_ids.add(cls.id)
        
    return jsonify(classes_data)

@classes_bp.route("/join", methods=["POST"])
@jwt_required()
def join_class():
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    data = request.json
    code = data.get("code")
    
    if not code:
        return jsonify({"msg": "Class code is required"}), 400
        
    cls = Class.query.filter_by(code=code.upper()).first()
    if not cls:
        return jsonify({"msg": "Invalid class code"}), 404
        
    if cls in user.enrolled_classes:
        return jsonify({"msg": "Already enrolled in this class"}), 400
        
    user.enrolled_classes.append(cls)
    db.session.commit()
    
    return jsonify({
        "msg": f"Successfully joined {cls.name}",
        "class": {
            "id": cls.id,
            "name": cls.name,
            "section": cls.section,
            "teacher": cls.teacher.full_name
        }
    })

# For testing purposes: Create Class
@classes_bp.route("/", methods=["POST"])
@jwt_required()
def create_class():
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    if not user or not user.is_teacher:
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Only teachers can create classes.", "details": {}}}), 403
    
    data = request.json
    name = data.get("name")
    section = data.get("section")
    
    new_class = Class(name=name, teacher_id=user.id, section=section)
    db.session.add(new_class)
    db.session.commit()
    
    return jsonify({
        "msg": "Class created",
        "code": new_class.code,
        "id": new_class.id
    }), 201
