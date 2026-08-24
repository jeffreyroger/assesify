import os
import time
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from app.models.users import db, User
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity, decode_token, get_jwt
from app.core.security import hash_password
from app.core.rate_limit import ratelimit_for_auth

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/upload-avatar", methods=["POST"])
@jwt_required()
def upload_avatar():
    current_user_id = get_jwt_identity()
    user = User.query.get(int(current_user_id))
    
    if not user:
        return jsonify({"msg": "User not found"}), 404
        
    if "file" not in request.files:
        return jsonify({"msg": "No file part"}), 400
        
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"msg": "No selected file"}), 400
        
    if file:
        filename = secure_filename(file.filename)
        ext = filename.rsplit(".", 1)[1].lower() if "." in filename else "jpg"
        new_filename = f"avatar_{user.id}_{int(time.time())}.{ext}"
        
        # Save to uploads/avatars
        project_root = os.path.abspath(os.path.join(current_app.root_path, ".."))
        avatar_dir = os.path.join(project_root, "uploads", "avatars")
        os.makedirs(avatar_dir, exist_ok=True)
        
        save_path = os.path.join(avatar_dir, new_filename)
        file.save(save_path)
        
        # Update user profile_pic path
        user.profile_pic = f"avatars/{new_filename}"
        db.session.commit()
        
        return jsonify({
            "msg": "Avatar uploaded successfully",
            "profile_pic": user.profile_pic
        }), 200

@auth_bp.route("/avatars/<path:filename>", methods=["GET"])
def get_avatar(filename):
    from flask import send_from_directory
    project_root = os.path.abspath(os.path.join(current_app.root_path, ".."))
    avatar_dir = os.path.join(project_root, "uploads", "avatars")
    return send_from_directory(avatar_dir, filename)

@auth_bp.route("/register", methods=["POST"])
@ratelimit_for_auth(limit=60)
def register():
    data = request.json
    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"msg": "Email already registered"}), 400

    user = User(
        email=data["email"],
        full_name=data["full_name"],
        is_teacher=data.get("is_teacher", False)
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()
    return jsonify({"msg": "User registered successfully"}), 201


# Helper: persist refresh token jti in DB for rotation / revocation
from app.models.refresh_token import RefreshToken
from datetime import datetime


def _store_refresh_token(token: str, user_id: int):
    try:
        decoded = decode_token(token)
        jti = decoded.get("jti")
        exp = decoded.get("exp")
        if jti and exp:
            expires_at = datetime.utcfromtimestamp(exp)
            rt = RefreshToken(jti=jti, user_id=int(user_id), expires_at=expires_at)
            db.session.add(rt)
            db.session.commit()
    except Exception:
        # best-effort: do not fail login if storage fails
        current_app.logger.exception("Failed to store refresh token")

@auth_bp.route("/login", methods=["POST"])
@ratelimit_for_auth(limit=60)
def login():
    data = request.json
    user = User.query.filter_by(email=data["email"]).first()
    if not user or not user.check_password(data["password"]):
        return jsonify({"msg": "Invalid credentials"}), 401

    # Security improvement: transparently upgrade legacy password hashes to argon2 when available.
    # Do a best-effort check for argon2 presence and existing hash format; do not fail login if re-hash fails.
    try:
        import importlib
        argon2_spec = importlib.util.find_spec("argon2")
        if argon2_spec is not None:
            # If stored hash does not look like an argon2 hash, re-hash using hash_password (which prefers argon2)
            if not (isinstance(user.password_hash, str) and user.password_hash.lower().startswith("$argon2")):
                try:
                    user.password_hash = hash_password(data["password"])
                    db.session.add(user)
                    db.session.commit()
                except Exception:
                    current_app.logger.exception("Failed to upgrade password hash for user %s", user.id)
    except Exception:
        # If anything about the detection fails, skip rehash silently
        pass

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    # persist refresh token jti for rotation/revocation
    _store_refresh_token(refresh_token, user.id)
    user_data = user.to_dict()
    user_data["access_token"] = access_token
    user_data["refresh_token"] = refresh_token
    return jsonify(user_data)

@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    # Revoke the incoming refresh token and issue a new one (rotation)
    try:
        current = get_jwt()
        incoming_jti = current.get("jti")
        if incoming_jti:
            row = RefreshToken.query.filter_by(jti=incoming_jti, revoked=False).first()
            if row:
                row.revoked = True
                db.session.commit()
    except Exception:
        current_app.logger.exception("Failed to revoke incoming refresh token")

    access_token = create_access_token(identity=get_jwt_identity())
    new_refresh = create_refresh_token(identity=get_jwt_identity())
    _store_refresh_token(new_refresh, int(get_jwt_identity()))
    return jsonify({"access_token": access_token, "refresh_token": new_refresh})

@auth_bp.route("/karmayogi/link", methods=["POST"])
@jwt_required()
def link_karmayogi():
    data = request.get_json(silent=True) or {}
    karmayogi_user_id = data.get("karmayogi_user_id")
    if not karmayogi_user_id:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "karmayogi_user_id is required", "details": {}}}), 400
    user = User.query.get(int(get_jwt_identity()))
    user.karmayogi_user_id = str(karmayogi_user_id)
    db.session.commit()
    return jsonify({"karmayogi_user_id": user.karmayogi_user_id})

@auth_bp.route("/update-profile", methods=["PUT"])
@jwt_required()
def update_profile():
    current_user_id = get_jwt_identity()
    user = User.query.get(int(current_user_id))
    
    if not user:
        return jsonify({"msg": "User not found"}), 404
        
    data = request.json
    if "full_name" in data:
        user.full_name = data["full_name"]
    if "major" in data:
        user.major = data["major"]
    if "location" in data:
        user.location = data["location"]
        
    db.session.commit()
    
    return jsonify({
        "msg": "Profile updated successfully",
        "user": user.to_dict()
    }), 200

@auth_bp.route("/profile", methods=["GET"])
@jwt_required()
def get_profile():
    current_user_id = get_jwt_identity()
    user = User.query.get(int(current_user_id))
    
    if not user:
        return jsonify({"msg": "User not found"}), 404
        
    # Gamification: Check for streak loss and health regeneration
    from datetime import date, timedelta
    today = date.today()
    if user.last_active_date:
        if user.last_active_date < today - timedelta(days=1):
            user.streak = 0 # Missed a day!
            
        # Optional: Regenerate health if it's a new day
        if user.last_active_date < today:
            user.health = 5 # Daily health reset
            user.last_active_date = today # Mark as seen today
            
        db.session.commit()

    return jsonify(user.to_dict()), 200
