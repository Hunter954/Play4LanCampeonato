import re
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, abort, flash
from flask_login import current_user, login_required
from web.extensions import db
from web.models import Tournament, TournamentRegistration, Server, Match, Demo, ServerCommand, MatchEvent

bp = Blueprint('admin', __name__, url_prefix='/admin')

SAFE_MAP = re.compile(r'^[a-z0-9_]+$', re.I)


def admin_only(fn):
    @wraps(fn)
    @login_required
    def inner(*a, **k):
        if not current_user.is_admin:
            abort(403)
        return fn(*a, **k)
    return inner


def queue_command(server, command, payload=None):
    if not server.host_id:
        abort(409)
    row = ServerCommand(host_id=server.host_id, server_code=server.code, command=command, payload=payload or {})
    db.session.add(row)
    db.session.commit()
    return row


@bp.get('/')
@admin_only
def dashboard():
    return render_template(
        'admin/dashboard.html',
        servers=Server.query.order_by(Server.code).all(),
        regs=TournamentRegistration.query.order_by(TournamentRegistration.id.desc()).limit(20).all(),
        matches=Match.query.order_by(Match.id.desc()).limit(20).all(),
    )


@bp.route('/tournaments/create', methods=['GET', 'POST'])
@admin_only
def create_tournament():
    if request.method == 'POST':
        t = Tournament(name=request.form['name'], description=request.form.get('description'), max_teams=int(request.form.get('max_teams', 16)))
        db.session.add(t)
        db.session.commit()
        return redirect(url_for('tournaments.detail', tid=t.id))
    return render_template('admin/create_tournament.html')


@bp.post('/registration/<int:rid>/<status>')
@admin_only
def registration_status(rid, status):
    if status not in {'APPROVED', 'REJECTED'}:
        abort(400)
    r = TournamentRegistration.query.get_or_404(rid)
    r.status = status
    db.session.commit()
    return redirect(url_for('admin.dashboard'))


@bp.post('/servers/<code>/<action>')
@admin_only
def server_action(code, action):
    if action not in {'START', 'STOP', 'RESTART'}:
        abort(400)
    s = Server.query.filter_by(code=code).first_or_404()
    queue_command(s, action)
    return redirect(url_for('admin.server_detail', code=code))


@bp.get('/servers/<code>')
@admin_only
def server_detail(code):
    s = Server.query.filter_by(code=code).first_or_404()
    latest_status = MatchEvent.query.filter_by(server_id=code, event_type='SERVER_STATUS').order_by(MatchEvent.id.desc()).first()
    commands = ServerCommand.query.filter_by(server_code=code).order_by(ServerCommand.id.desc()).limit(30).all()
    telemetry = latest_status.payload if latest_status else {}
    return render_template('admin/server_detail.html', server=s, telemetry=telemetry or {}, commands=commands)


@bp.post('/servers/<code>/rcon')
@admin_only
def server_rcon(code):
    s = Server.query.filter_by(code=code).first_or_404()
    command = (request.form.get('command') or '').strip()
    if not command or len(command) > 500:
        abort(400)
    queue_command(s, 'RCON', {'command': command})
    flash(f'Comando enviado ao {code}: {command}', 'success')
    return redirect(url_for('admin.server_detail', code=code))


@bp.post('/servers/<code>/quick/<action>')
@admin_only
def server_quick_action(code, action):
    s = Server.query.filter_by(code=code).first_or_404()
    simple = {
        'STATUS': 'status',
        'WARMUP_END': 'mp_warmup_end',
        'RESTART_ROUND': 'mp_restartgame 1',
        'PAUSE': 'mp_pause_match',
        'UNPAUSE': 'mp_unpause_match',
    }
    if action not in simple:
        abort(400)
    queue_command(s, 'RCON', {'command': simple[action]})
    return redirect(url_for('admin.server_detail', code=code))


@bp.post('/servers/<code>/map')
@admin_only
def server_change_map(code):
    s = Server.query.filter_by(code=code).first_or_404()
    map_name = (request.form.get('map_name') or '').strip().lower()
    if not SAFE_MAP.match(map_name):
        flash('Nome de mapa inválido.', 'danger')
        return redirect(url_for('admin.server_detail', code=code))
    queue_command(s, 'RCON', {'command': f'changelevel {map_name}'})
    return redirect(url_for('admin.server_detail', code=code))


@bp.post('/servers/<code>/kick')
@admin_only
def server_kick(code):
    s = Server.query.filter_by(code=code).first_or_404()
    userid = (request.form.get('userid') or '').strip()
    if not userid.isdigit():
        abort(400)
    # kickid usa userid retornado por status e evita problemas com nomes contendo espaços.
    queue_command(s, 'RCON', {'command': f'kickid {userid}'})
    return redirect(url_for('admin.server_detail', code=code))
