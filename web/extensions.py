from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.entrar"
login_manager.login_message = "Entre com sua Steam para continuar."
login_manager.login_message_category = "info"

try:
    import gevent  # noqa: F401
    _async_mode = 'gevent'
except ImportError:
    _async_mode = 'threading'

socketio = SocketIO(cors_allowed_origins="*", async_mode=_async_mode)
