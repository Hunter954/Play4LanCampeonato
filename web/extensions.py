from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
socketio = SocketIO(cors_allowed_origins="*", async_mode="gevent")
