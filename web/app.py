import os
from pathlib import Path
from flask import Flask
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash
from web.extensions import db, login_manager, socketio

load_dotenv()

# create_all() não altera tabelas existentes; colunas novas entram aqui.
ADDED_COLUMNS = {
    'user': {'whatsapp': 'VARCHAR(32)', 'city': 'VARCHAR(80)', 'bio': 'VARCHAR(280)', 'onboarded_at': 'TIMESTAMP', 'last_login_at': 'TIMESTAMP'},
    'team': {'description': 'VARCHAR(280)'},
    'tournament': {'starts_at': 'TIMESTAMP', 'location': 'VARCHAR(160)', 'prize': 'TEXT', 'rules': 'TEXT', 'entry_fee_cents': 'INTEGER DEFAULT 0',
                   'bo_default': 'INTEGER DEFAULT 1', 'bo_upper_final': 'INTEGER DEFAULT 3', 'bo_lower_final': 'INTEGER DEFAULT 1', 'bo_grand_final': 'INTEGER DEFAULT 3'},
    'tournament_registration': {'seed': 'INTEGER', 'paid_at': 'TIMESTAMP', 'admin_note': 'VARCHAR(280)'},
    'match': {'bracket': 'VARCHAR(10)', 'round': 'INTEGER', 'position': 'INTEGER', 'label': 'VARCHAR(60)', 'team1_from': 'VARCHAR(20)', 'team2_from': 'VARCHAR(20)',
              'next_match_id': 'INTEGER', 'next_slot': 'INTEGER', 'loser_match_id': 'INTEGER', 'loser_slot': 'INTEGER', 'winner_id': 'INTEGER',
              'walkover': 'BOOLEAN DEFAULT FALSE', 'config_token': 'VARCHAR(64)', 'started_at': 'TIMESTAMP', 'finished_at': 'TIMESTAMP'},
}

STATUS_LABELS = {
    'REGISTRATION': 'Inscrições abertas', 'CHECKIN': 'Check-in', 'CLOSED': 'Inscrições encerradas', 'RUNNING': 'Em andamento', 'LIVE': 'Ao vivo', 'FINISHED': 'Finalizado', 'CANCELLED': 'Cancelado',
    'SCHEDULED': 'Agendada', 'PENDING': 'Em análise', 'APPROVED': 'Confirmado', 'REJECTED': 'Recusado',
    'AWAITING_PAYMENT': 'Aguardando pagamento', 'PAYMENT_REVIEW': 'Pagamento em análise',
    'WAITING': 'Aguardando times', 'READY': 'Pronta', 'VETO': 'Veto de mapas', 'CONFIGURED': 'Mapas definidos', 'LOADED': 'No servidor',
    'UPPER': 'Upper', 'LOWER': 'Lower', 'FINAL': 'Grande final',
    'DOUBLE_ELIMINATION': 'Dupla eliminação', 'SINGLE_ELIMINATION': 'Eliminação simples', 'SWISS': 'Suíço', 'ROUND_ROBIN': 'Pontos corridos',
}

def _ensure_columns():
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)
    for table, cols in ADDED_COLUMNS.items():
        if not insp.has_table(table): continue
        existing = {c['name'] for c in insp.get_columns(table)}
        for name, ddl in cols.items():
            if name not in existing:
                db.session.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ddl}'))
    db.session.commit()

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    # Railway termina o HTTPS no proxy; sem isso os links externos (login Steam, convites) saem como http://
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")
    db_url = os.getenv("DATABASE_URL", "sqlite:///dev.db")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql://") and "+psycopg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH_MB", "1024")) * 1024 * 1024
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"; app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
    db.init_app(app); login_manager.init_app(app); socketio.init_app(app)

    @app.template_filter('label')
    def label_filter(value): return STATUS_LABELS.get(str(value or '').upper(), str(value or '').replace('_', ' ').title())

    @app.errorhandler(404)
    def not_found(e):
        from flask import request, render_template
        if request.path.startswith(('/api', '/admin', '/static')): return e
        return render_template('errors/404.html'), 404

    from web.models import User
    @login_manager.user_loader
    def load_user(uid): return db.session.get(User, int(uid))

    from web.routes.main import bp as main_bp
    from web.routes.auth import bp as auth_bp
    from web.routes.teams import bp as teams_bp
    from web.routes.tournaments import bp as tournaments_bp
    from web.routes.admin import bp as admin_bp
    from web.routes.api import bp as api_bp
    from web.routes.matches import bp as matches_bp
    from web.routes.admin_tournaments import bp as admin_t_bp
    app.register_blueprint(main_bp); app.register_blueprint(auth_bp); app.register_blueprint(teams_bp)
    app.register_blueprint(tournaments_bp); app.register_blueprint(admin_bp); app.register_blueprint(api_bp)
    app.register_blueprint(matches_bp); app.register_blueprint(admin_t_bp)

    with app.app_context():
        db.create_all(); _ensure_columns()
        email=os.getenv("ADMIN_EMAIL"); pwd=os.getenv("ADMIN_PASSWORD")
        if email and pwd and not User.query.filter_by(email=email).first():
            db.session.add(User(email=email, password_hash=generate_password_hash(pwd), is_admin=True, nickname="ADMIN")); db.session.commit()
    return app
