import re
from datetime import datetime
from functools import wraps

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from web.extensions import db, socketio
from web.models import Match, MatchEvent, Server, ServerCommand, Tournament, TournamentRegistration
from web.live_state import get_server_state
from web.player_identity import enrich_telemetry

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


def _is_ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'


def _dt(value):
    return value.isoformat() + 'Z' if value else None


def _latest_telemetry(code):
    live = get_server_state(code)
    if live is not None:
        return enrich_telemetry(live.get('telemetry') or {})
    event = (
        MatchEvent.query
        .filter_by(server_id=code, event_type='SERVER_STATUS')
        .order_by(MatchEvent.id.desc())
        .first()
    )
    return enrich_telemetry(event.payload or {}) if event else {}


def _server_snapshot(server, telemetry=None):
    telemetry = telemetry if telemetry is not None else _latest_telemetry(server.code)
    return {
        'code': server.code,
        'display_name': server.display_name or server.code,
        'host_id': server.host_id,
        'status': server.status or 'UNKNOWN',
        'last_heartbeat': _dt(server.last_heartbeat),
        'current_match_id': server.current_match_id,
        'telemetry': telemetry or {},
    }


def _command_snapshot(command):
    payload = dict(command.payload or {})
    return {
        'id': command.id,
        'server_code': command.server_code,
        'command': command.command,
        'status': command.status,
        'created_at': _dt(command.created_at),
        'completed_at': _dt(command.completed_at),
        'rcon_command': payload.get('command'),
        'result': payload.get('_result'),
        'error': payload.get('_error'),
    }


def queue_command(server, command, payload=None):
    if not server.host_id:
        abort(409)
    row = ServerCommand(host_id=server.host_id, server_code=server.code, command=command, payload=payload or {})
    db.session.add(row)
    db.session.commit()
    socketio.emit('server_command', _command_snapshot(row))
    return row


def _queued_response(server, row, fallback_endpoint='admin.server_detail'):
    if _is_ajax():
        return jsonify(ok=True, server=_server_snapshot(server), command=_command_snapshot(row)), 202
    return redirect(url_for(fallback_endpoint, code=server.code))


@bp.get('/')
@admin_only
def dashboard():
    servers = Server.query.order_by(Server.code).all()
    server_states = {s.code: _latest_telemetry(s.code) for s in servers}
    regs = TournamentRegistration.query.order_by(TournamentRegistration.id.desc()).limit(20).all()
    matches = Match.query.order_by(Match.id.desc()).limit(10).all()
    pending_count = TournamentRegistration.query.filter_by(status='PENDING').count()
    online_count = sum(1 for s in servers if (s.status or '').upper() == 'ONLINE')
    players_total = sum(int((server_states.get(s.code) or {}).get('player_count') or 0) for s in servers)
    return render_template(
        'admin/dashboard.html',
        servers=servers,
        server_states=server_states,
        regs=regs,
        matches=matches,
        pending_count=pending_count,
        online_count=online_count,
        players_total=players_total,
    )


@bp.get('/api/overview')
@admin_only
def admin_overview_api():
    servers = Server.query.order_by(Server.code).all()
    snapshots = [_server_snapshot(s) for s in servers]
    return jsonify(
        ok=True,
        servers=snapshots,
        summary={
            'servers_online': sum(1 for s in snapshots if s['status'].upper() == 'ONLINE'),
            'servers_total': len(snapshots),
            'players_total': sum(int((s['telemetry'] or {}).get('player_count') or 0) for s in snapshots),
            'pending_registrations': TournamentRegistration.query.filter_by(status='PENDING').count(),
            'matches_active': Match.query.filter(Match.status.in_(['LIVE', 'READY', 'VETO'])).count(),
        },
    )


@bp.get('/api/servers/<code>/state')
@admin_only
def server_state_api(code):
    server = Server.query.filter_by(code=code).first_or_404()
    commands = ServerCommand.query.filter_by(server_code=code).order_by(ServerCommand.id.desc()).limit(30).all()
    return jsonify(
        ok=True,
        server=_server_snapshot(server),
        commands=[_command_snapshot(c) for c in commands],
    )


@bp.route('/tournaments/create', methods=['GET', 'POST'])
@admin_only
def create_tournament():
    if request.method == 'POST':
        t = Tournament(
            name=request.form['name'],
            description=request.form.get('description'),
            max_teams=int(request.form.get('max_teams', 16)),
        )
        db.session.add(t)
        db.session.commit()
        return redirect(url_for('tournaments.detail', tid=t.id))
    return render_template('admin/create_tournament.html')


@bp.post('/registration/<int:rid>/<status>')
@admin_only
def registration_status(rid, status):
    if status not in {'APPROVED', 'REJECTED'}:
        abort(400)
    registration = TournamentRegistration.query.get_or_404(rid)
    registration.status = status
    db.session.commit()
    if _is_ajax():
        return jsonify(ok=True, id=registration.id, status=registration.status)
    return redirect(url_for('admin.dashboard'))


@bp.post('/servers/<code>/<action>')
@admin_only
def server_action(code, action):
    if action not in {'START', 'STOP', 'RESTART'}:
        abort(400)
    server = Server.query.filter_by(code=code).first_or_404()
    row = queue_command(server, action)
    return _queued_response(server, row)


@bp.get('/servers/<code>')
@admin_only
def server_detail(code):
    server = Server.query.filter_by(code=code).first_or_404()
    telemetry = _latest_telemetry(code)
    commands = ServerCommand.query.filter_by(server_code=code).order_by(ServerCommand.id.desc()).limit(30).all()
    return render_template('admin/server_detail.html', server=server, telemetry=telemetry, commands=commands)


@bp.post('/servers/<code>/rcon')
@admin_only
def server_rcon(code):
    server = Server.query.filter_by(code=code).first_or_404()
    command = (request.form.get('command') or '').strip()
    if not command or len(command) > 500:
        abort(400)
    row = queue_command(server, 'RCON', {'command': command})
    if _is_ajax():
        return jsonify(ok=True, command=_command_snapshot(row)), 202
    flash(f'Comando enviado ao {code}: {command}', 'success')
    return redirect(url_for('admin.server_detail', code=code))


@bp.post('/servers/<code>/quick/<action>')
@admin_only
def server_quick_action(code, action):
    server = Server.query.filter_by(code=code).first_or_404()
    simple = {
        'STATUS': 'status',
        'READY_STATUS': 'css_prontos',
        'SCORE': 'css_placar',
        'PAUSES': 'css_pausas',
        'KNIFE': 'css_faca',
        'WARMUP_END': 'mp_warmup_end',
        'RESTART_ROUND': 'mp_restartgame 1',
        'PAUSE': 'mp_pause_match',
        'UNPAUSE': 'mp_unpause_match',
        'RESUME_PLAY4LAN': 'css_voltar',
    }
    if action not in simple:
        abort(400)
    row = queue_command(server, 'RCON', {'command': simple[action]})
    return _queued_response(server, row)


@bp.post('/servers/<code>/map')
@admin_only
def server_change_map(code):
    server = Server.query.filter_by(code=code).first_or_404()
    map_name = (request.form.get('map_name') or '').strip().lower()
    if not SAFE_MAP.match(map_name):
        if _is_ajax():
            return jsonify(ok=False, error='Nome de mapa inválido.'), 400
        flash('Nome de mapa inválido.', 'danger')
        return redirect(url_for('admin.server_detail', code=code))
    row = queue_command(server, 'RCON', {'command': f'changelevel {map_name}'})
    return _queued_response(server, row)


@bp.post('/servers/<code>/kick')
@admin_only
def server_kick(code):
    server = Server.query.filter_by(code=code).first_or_404()
    userid = (request.form.get('userid') or '').strip()
    if not userid.isdigit():
        abort(400)
    row = queue_command(server, 'RCON', {'command': f'kickid {userid}'})
    return _queued_response(server, row)
