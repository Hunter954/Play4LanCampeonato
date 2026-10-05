import re
from functools import wraps

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash

from web.extensions import db, socketio
from web.live_state import get_server_state
from web.models import AdminSetting, Match, MatchEvent, Server, ServerCommand, Tournament, TournamentRegistration, User
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


STATUS_TEXT = {'ONLINE':'Online','OFFLINE':'Desligado','STARTING':'Iniciando','UPDATING':'Atualizando','NO_SIGNAL':'Agent sem sinal'}


def _server_snapshot(server, telemetry=None):
    telemetry = telemetry if telemetry is not None else _latest_telemetry(server.code)
    status = server.live_status
    if status == 'NO_SIGNAL': telemetry = {**(telemetry or {}), 'players': [], 'player_count': 0, 'online': False, 'rcon_ok': False}
    return {'code':server.code,'display_name':server.display_name or server.code,'host_id':server.host_id,
            'status':status,'status_label':STATUS_TEXT.get(status,status),'last_heartbeat':_dt(server.last_heartbeat),
            'current_match_id':server.current_match_id,'telemetry':telemetry or {},
            'version':{'installed':server.installed_version,'required':server.required_version,'up_to_date':server.up_to_date,
                       'update_state':server.update_state,'update_message':server.update_message,'auto_update':server.auto_update is not False}}


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


REVIEW_STATUSES = ('PENDING', 'PAYMENT_REVIEW')


@bp.app_context_processor
def _admin_nav():
    def admin_nav():
        servers = Server.query.order_by(Server.code).all()
        return {'servers': servers, 'outdated': sum(1 for s in servers if s.needs_update), 'pending': _pending_registrations(),
                'tournaments': Tournament.query.filter(Tournament.status != 'FINISHED').order_by(Tournament.id.desc()).limit(4).all()}
    return {'admin_nav': admin_nav}


def _pending_registrations():
    return TournamentRegistration.query.filter(TournamentRegistration.status.in_(REVIEW_STATUSES)).count()


def _server_page(code, template, **extra):
    server=Server.query.filter_by(code=code).first_or_404(); telemetry=_server_snapshot(server)['telemetry']
    match=db.session.get(Match, server.current_match_id) if server.current_match_id else None
    return render_template(template, server=server, telemetry=telemetry, maps=MAPS, current_match=match, **extra)


@bp.get('/')
@admin_only
def dashboard():
    servers=Server.query.order_by(Server.code).all(); snaps={s.code:_server_snapshot(s) for s in servers}
    active=Tournament.query.filter(Tournament.status.in_(('REGISTRATION','CLOSED','RUNNING'))).order_by(Tournament.id.desc()).all()
    live=Match.query.filter(Match.status.in_(('LIVE','LOADED','VETO','CONFIGURED'))).order_by(Match.id).all()
    ready=Match.query.filter_by(status='READY').order_by(Match.id).limit(8).all()
    return render_template('admin/dashboard.html',servers=servers,snaps=snaps,active_tournaments=active,live_matches=live,ready_matches=ready,
        pending_count=_pending_registrations(),
        regs=TournamentRegistration.query.filter(TournamentRegistration.status.in_(REVIEW_STATUSES)).order_by(TournamentRegistration.id.desc()).limit(8).all(),
        online_count=sum(1 for s in servers if s.live_status=='ONLINE'),
        outdated=[s for s in servers if s.needs_update],
        players_total=sum(int(snaps[s.code]['telemetry'].get('player_count') or 0) for s in servers))

@bp.get('/api/overview')
@admin_only
def admin_overview_api():
    servers=Server.query.order_by(Server.code).all(); snaps=[_server_snapshot(s) for s in servers]
    return jsonify(ok=True,servers=snaps,summary={'servers_online':sum(1 for s in snaps if s['status']=='ONLINE'),
        'servers_total':len(snaps),'players_total':sum(int((s['telemetry'] or {}).get('player_count') or 0) for s in snaps),
        'pending_registrations':_pending_registrations()})

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
def server_security(code): return redirect(url_for('admin.security'))

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
    if action not in {'START','STOP','RESTART','UPDATE','CHECK_UPDATE'}: abort(400)
    denied=_require_pin()
    if denied:return denied
    server=Server.query.filter_by(code=code).first_or_404()
    if not server.has_signal:
        return jsonify(ok=False,error='O Agent deste servidor está sem sinal. Abra o Agent no PC da LAN antes.'),409
    if action=='UPDATE':
        match=db.session.get(Match, server.current_match_id) if server.current_match_id else None
        if match and match.status in ('LOADED','LIVE'):
            return jsonify(ok=False,error='Há uma partida em andamento neste servidor. Termine ou libere a partida antes de atualizar.'),409
        server.update_state='RUNNING'; server.update_message='Comando enviado ao Agent...'
    return _queued(server,queue_command(server,action))

@bp.post('/servers/<code>/auto-update')
@admin_only
def server_auto_update(code):
    server=Server.query.filter_by(code=code).first_or_404()
    server.auto_update=request.form.get('enabled')=='1'; db.session.commit()
    msg='Atualização automática ligada: o servidor atualiza sozinho quando estiver vazio e sem partida.' if server.auto_update else 'Atualização automática desligada.'
    return jsonify(ok=True,message=msg,reload=True) if _is_ajax() else redirect(url_for('admin.server_detail',code=code))

@bp.get('/servers/')
@admin_only
def servers_list():
    servers=Server.query.order_by(Server.code).all()
    return render_template('admin/servers.html',servers=servers,snaps={s.code:_server_snapshot(s) for s in servers})

@bp.get('/jogadores')
@admin_only
def players_admin():
    q=(request.args.get('q') or '').strip()
    query=User.query
    if q:
        like=f'%{q}%'; query=query.filter(db.or_(User.nickname.ilike(like),User.steam_name.ilike(like),User.real_name.ilike(like),User.steam_id64.ilike(like),User.email.ilike(like)))
    users=query.order_by(User.is_admin.desc(),User.created_at.desc()).limit(300).all()
    return render_template('admin/players.html',users=users,q=q,total=User.query.count())

@bp.post('/jogadores/<int:uid>/admin')
@admin_only
def toggle_admin(uid):
    denied=_require_pin()
    if denied:return denied
    u=db.get_or_404(User,uid)
    if u.id==current_user.id: return jsonify(ok=False,error='Você não pode remover o seu próprio acesso de admin.'),400
    u.is_admin=not u.is_admin; db.session.commit()
    return jsonify(ok=True,message=f"{u.display_name} {'agora é admin' if u.is_admin else 'não é mais admin'}.",reload=True)

@bp.get('/seguranca')
@admin_only
def security():
    return render_template('admin/security.html')

@bp.post('/seguranca/pin')
@admin_only
def security_pin():
    denied=_require_pin()
    if denied: return denied
    new_pin=(request.form.get('new_pin') or '').strip(); confirm=(request.form.get('confirm_pin') or '').strip()
    if not re.fullmatch(r'\d{4}',new_pin) or new_pin!=confirm:
        return jsonify(ok=False,error='O novo PIN deve ter 4 dígitos e a confirmação precisa ser igual.'),400
    row=_pin_hash(); row.value=generate_password_hash(new_pin); db.session.commit()
    return jsonify(ok=True,message='PIN de operação alterado.')

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

@bp.post('/registration/<int:rid>/<status>')
@admin_only
def registration_status(rid,status):
    if status not in {'APPROVED','REJECTED'}:abort(400)
    row=TournamentRegistration.query.get_or_404(rid);row.status=status;db.session.commit()
    return jsonify(ok=True,id=row.id,status=row.status) if _is_ajax() else redirect(url_for('admin.dashboard'))
