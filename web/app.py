import os
from pathlib import Path
from flask import Flask
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from web.extensions import db, login_manager, socketio

load_dotenv()

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")
    db_url = os.getenv("DATABASE_URL", "sqlite:///dev.db")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql://") and "+psycopg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH_MB", "1024")) * 1024 * 1024
    db.init_app(app); login_manager.init_app(app); socketio.init_app(app)

    from web.models import User
    @login_manager.user_loader
    def load_user(uid): return db.session.get(User, int(uid))

    from web.routes.main import bp as main_bp
    from web.routes.auth import bp as auth_bp
    from web.routes.teams import bp as teams_bp
    from web.routes.tournaments import bp as tournaments_bp
    from web.routes.admin import bp as admin_bp
    from web.routes.api import bp as api_bp
    app.register_blueprint(main_bp); app.register_blueprint(auth_bp); app.register_blueprint(teams_bp)
    app.register_blueprint(tournaments_bp); app.register_blueprint(admin_bp); app.register_blueprint(api_bp)

    with app.app_context():
        db.create_all()
        email=os.getenv("ADMIN_EMAIL"); pwd=os.getenv("ADMIN_PASSWORD")
        if email and pwd and not User.query.filter_by(email=email).first():
            db.session.add(User(email=email, password_hash=generate_password_hash(pwd), is_admin=True, nickname="ADMIN")); db.session.commit()
    return app
