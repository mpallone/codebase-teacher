"""Sample Flask application for testing codebase-teacher."""

from flask import Flask, jsonify, request

from .models import User, db
from .tasks import send_welcome_email

app = Flask(__name__)


@app.route("/api/users", methods=["GET"])
def list_users():
    """List all users."""
    users = User.query.all()
    return jsonify([u.to_dict() for u in users])


@app.route("/api/users", methods=["POST"])
def create_user():
    """Create a new user."""
    data = request.get_json()
    user = User(name=data["name"], email=data["email"])
    db.session.add(user)
    db.session.commit()
    send_welcome_email.delay(user.id)
    return jsonify(user.to_dict()), 201


@app.route("/api/users/<int:user_id>", methods=["GET"])
def get_user(user_id: int):
    """Get a user by ID."""
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())
