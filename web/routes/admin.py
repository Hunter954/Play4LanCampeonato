import re
from functools import wraps

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash

from web.extensions import db, socketio
from web.live_state import get_server_state
from web.models import AdminSetting, Match, MatchEvent, Server, ServerCommand, Tournament, TournamentRegistration
from web.player_identity import enrich_telemetry

bp = Blueprint('admin', __name__, url_prefix='/admin')
SAFE_MAP = re.compile(r'^[a-z0-9_]+$', re.I)
SAFE_BACKUP = re.compile(r'^play4lan_[A-Za-z0-9_.-]+\.json$', re.I)
PIN_KEY = 'admin_action_pin_hash'
MAPS = [
    ('de_mirage','Mirage'),('de_inferno','Inferno'),('de_nuke','Nuke'),('de_ancient','Ancient'),
    ('de_anubis','Anubis'),('de_dust2','Dust II'),('de_train','Train'),('de_cache','Cache'),
]


def admin_only(fn):
    @wraps(fn)
    @login_required
    def inner(*a, **k):
        if not current_user.is_admin: abort(403)
        return fn(*a, **k)
    return inner


def _is_ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'


def _dt(value): return value.isoformat() + 'Z' if value else None


def _pin_hash():
    row = AdminSetting.query.filter_by(key=PIN_KEY).first()
    if not row:
        row = AdminSetting(key=PIN_KEY, value=generate_password_hash('0800'))
        db.session.add(row); db.session.commit()
    return row


def _require_pin():
    pin = (request.form.get('pin') or (request.get_json(silent=True) or {}).get('pin') or '').strip()
    if not re.fullmatch(r'\d{4}', pin) or not check_password_hash(_pin_hash().value, pin):
        if _is_ajax(): return jsonify(ok=False, error='PIN de operação inválido.'), 403
        abort(403)
    return None


def _latest_telemetry(code):
    live = get_server_state(code)
    if live is not None: return enrich_telemetry(live.get('telemetry') or {})
    event = MatchEvent.query.filter_by(server_id=code, event_type='SERVER_STATUS').order_by(MatchEvent.id.desc()).first()
    return enrich_telemetry(event.payload or {}) if event else {}


def _server_snapshot(server, telemetry=None):
    telemetry = telemetry if telemetry is not None else _latest_telemetry(server.code)
    return {'code':server.code,'display_name':server.display_name or server.code,'host_id':server.host_id,
            'status':server.status or 'UNKNOWN','last_heartbeat':_dt(server.last_heartbeat),
            'current_match_id':server.current_match_id,'telemetry':telemetry or {}}


def _command_snapshot(c):
    payload=dict(c.payload or {})
    return {'id':c.id,'server_code':c.server_code,'command':c.command,'status':c.status,'created_at':_dt(c.created_at),
            'completed_at':_dt(c.completed_at),'rcon_command':payload.get('command'),'result':payload.get('_result'),'error':payload.get('_error')}


def queue_command(server, command, payload=None):
    if not server.host_id: abort(409)
    row=ServerCommand(host_id=server.host_id,server_code=server.code,command=command,payload=payload or {})
    db.session.add(row); db.session.commit(); socketio.emit('server_command', _command_snapshot(row)); return row


def _queued(server,row):
    if _is_ajax(): return jsonify(ok=True,server=_server_snapshot(server),command=_command_snapshot(row)),202
    return redirect(url_for('admin.server_detail',code=server.code))


def _server_page(code, template, **extra):
    server=Server.query.filter_by(code=code).first_or_404(); telemetry=_latest_telemetry(code)
    return render_template(template, server=server, telemetry=telemetry, maps=MAPS, **extra)


@bp.get('/')
@admin_only
def dashboard():
    servers=Server.query.order_by(Server.code).all(); states={s.code:_latest_telemetry(s.code) for s in servers}
    return render_template('admin/dashboard.html',servers=servers,server_states=states,
        pending_count=TournamentRegistration.query.filter_by(status='PENDING').count(),
        online_count=sum(1 for s in servers if (s.status or '').upper()=='ONLINE'),
        players_total=sum(int((states.get(s.code) or {}).get('player_count') or 0) for s in servers),
        matches=Match.query.order_by(Match.id.desc()).limit(6).all())

@bp.get('/api/overview')
@admin_only
def admin_overview_api():
    servers=Server.query.order_by(Server.code).all(); snaps=[_server_snapshot(s) for s in servers]
    return jsonify(ok=True,servers=snaps,summary={'servers_online':sum(1 for s in snaps if s['status'].upper()=='ONLINE'),
        'servers_total':len(snaps),'players_total':sum(int((s['telemetry'] or {}).get('player_count') or 0) for s in snaps),
        'pending_registrations':TournamentRegistration.query.filter_by(status='PENDING').count()})

@bp.get('/api/servers/<code>/state')
@admin_only
def server_state_api(code):
    server=Server.query.filter_by(code=code).first_or_404()
    return jsonify(ok=True,server=_server_snapshot(server))

@bp.get('/servers/<code>')
@admin_only
def server_detail(code): return _server_page(code,'admin/server_overview.html')

@bp.get('/servers/<code>/players')
@admin_only
def server_players(code): return _server_page(code,'admin/server_players.html')

@bp.get('/servers/<code>/match')
@admin_only
def server_match(code): return _server_page(code,'admin/server_match.html')

@bp.get('/servers/<code>/chat')
@admin_only
def server_chat(code): return _server_page(code,'admin/server_chat.html')

@bp.get('/servers/<code>/backups')
@admin_only
def server_backups(code): return _server_page(code,'admin/server_backups.html')

@bp.get('/servers/<code>/logs')
@admin_only
def server_logs(code):
    commands=ServerCommand.query.filter_by(server_code=code).order_by(ServerCommand.id.desc()).limit(150).all()
    return _server_page(code,'admin/server_logs.html',commands=commands)

@bp.get('/servers/<code>/security')
@admin_only
def server_security(code): return _server_page(code,'admin/server_security.html')

@bp.post('/servers/<code>/security/pin')
@admin_only
def update_pin(code):
    denied=_require_pin()
    if denied: return denied
    new_pin=(request.form.get('new_pin') or '').strip(); confirm=(request.form.get('confirm_pin') or '').strip()
    if not re.fullmatch(r'\d{4}',new_pin) or new_pin!=confirm:
        return jsonify(ok=False,error='O novo PIN deve ter 4 dígitos e a confirmação precisa ser igual.'),400
    row=_pin_hash(); row.value=generate_password_hash(new_pin); db.session.commit()
    return jsonify(ok=True,message='PIN de operação alterado.')

@bp.post('/servers/<code>/<action>')
@admin_only
def server_action(code,action):
    if action not in {'START','STOP','RESTART'}: abort(400)
    denied=_require_pin()
    if denied:return denied
    server=Server.query.filter_by(code=code).first_or_404(); return _queued(server,queue_command(server,action))

@bp.post('/servers/<code>/quick/<action>')
@admin_only
def server_quick_action(code,action):
    denied=_require_pin()
    if denied:return denied
    commands={'READY_STATUS':'css_prontos','SCORE':'css_placar','PAUSES':'css_pausas','KNIFE':'css_faca',
              'PAUSE':'css_play4lan_admin_pause','RESUME':'css_play4lan_admin_resume',
              'WARMUP_END':'mp_warmup_end','RESTART_ROUND':'mp_restartgame 1','TEST_ON':'play4lan_test_mode 1','TEST_OFF':'play4lan_test_mode 0'}
    if action not in commands:abort(400)
    server=Server.query.filter_by(code=code).first_or_404(); return _queued(server,queue_command(server,'RCON',{'command':commands[action]}))

@bp.post('/servers/<code>/map')
@admin_only
def server_change_map(code):
    denied=_require_pin()
    if denied:return denied
    server=Server.query.filter_by(code=code).first_or_404(); name=(request.form.get('map_name') or '').strip().lower()
    if not SAFE_MAP.match(name):return jsonify(ok=False,error='Mapa inválido.'),400
    return _queued(server,queue_command(server,'RCON',{'command':f'changelevel {name}'}))

@bp.post('/servers/<code>/players/<int:userid>/<state>')
@admin_only
def player_ready(code,userid,state):
    denied=_require_pin()
    if denied:return denied
    if state not in {'ready','wait'}:abort(400)
    server=Server.query.filter_by(code=code).first_or_404(); value='1' if state=='ready' else '0'
    return _queued(server,queue_command(server,'RCON',{'command':f'css_play4lan_ready {userid} {value}'}))

@bp.post('/servers/<code>/kick')
@admin_only
def server_kick(code):
    denied=_require_pin()
    if denied:return denied
    uid=(request.form.get('userid') or '').strip()
    if not uid.isdigit():abort(400)
    server=Server.query.filter_by(code=code).first_or_404(); return _queued(server,queue_command(server,'RCON',{'command':f'kickid {uid}'}))

@bp.post('/servers/<code>/restore')
@admin_only
def server_restore(code):
    denied=_require_pin()
    if denied:return denied
    filename=(request.form.get('backup') or '').strip()
    if not SAFE_BACKUP.fullmatch(filename):return jsonify(ok=False,error='Backup inválido.'),400
    server=Server.query.filter_by(code=code).first_or_404(); return _queued(server,queue_command(server,'RCON',{'command':f'css_play4lan_restore {filename}'}))

@bp.post('/servers/<code>/rcon')
@admin_only
def server_rcon(code):
    denied=_require_pin()
    if denied:return denied
    command=(request.form.get('command') or '').strip()
    if not command or len(command)>500:abort(400)
    server=Server.query.filter_by(code=code).first_or_404(); return _queued(server,queue_command(server,'RCON',{'command':command}))

@bp.route('/tournaments/create',methods=['GET','POST'])
@admin_only
def create_tournament():
    if request.method=='POST':
        t=Tournament(name=request.form['name'],description=request.form.get('description'),max_teams=int(request.form.get('max_teams',16)))
        db.session.add(t);db.session.commit();return redirect(url_for('tournaments.detail',tid=t.id))
    return render_template('admin/create_tournament.html')

@bp.post('/registration/<int:rid>/<status>')
@admin_only
def registration_status(rid,status):
    if status not in {'APPROVED','REJECTED'}:abort(400)
    row=TournamentRegistration.query.get_or_404(rid);row.status=status;db.session.commit()
    return jsonify(ok=True,id=row.id,status=row.status) if _is_ajax() else redirect(url_for('admin.dashboard'))
