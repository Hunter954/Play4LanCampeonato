import random
from datetime import datetime
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from web.extensions import db, socketio
from web.models import Match, Server, Tournament, TournamentRegistration, ACTIVE_REG_STATUSES, ROSTER_SIZE
from web.maps import ALL_MAPS
from web.routes.admin import admin_only, queue_command, _require_pin, _is_ajax
from web import bracket, veto, registrations, matchzy, payments

bp = Blueprint('admin_t', __name__, url_prefix='/admin/tournaments')
STATUSES = ['REGISTRATION', 'CLOSED', 'RUNNING', 'FINISHED']


def _t(tid): return db.get_or_404(Tournament, tid)


def _done(message, url, category='success'):
    if _is_ajax(): return jsonify(ok=True, message=message, reload=True)
    flash(message, category); return redirect(url)


def _fail(message, url):
    if _is_ajax(): return jsonify(ok=False, error=message), 400
    flash(message, 'danger'); return redirect(url)


@bp.get('/')
@admin_only
def index():
    return render_template('admin/tournaments/index.html', tournaments=Tournament.query.order_by(Tournament.id.desc()).all())


def _save_form(t, f):
    t.name = (f.get('name') or '').strip()[:160] or t.name
    t.description = (f.get('description') or '').strip() or None
    t.location = (f.get('location') or '').strip()[:160] or None
    t.prize = (f.get('prize') or '').strip() or None
    t.rules = (f.get('rules') or '').strip() or None
    t.max_teams = max(2, min(32, int(f.get('max_teams') or 16)))
    fee = (f.get('entry_fee') or '0').replace('R$', '').replace('.', '').replace(',', '.').strip() or '0'
    t.entry_fee_cents = max(0, round(float(fee) * 100))
    starts = (f.get('starts_at') or '').strip()
    t.starts_at = datetime.fromisoformat(starts) if starts else None
    maps = [m for m in f.getlist('maps') if m in ALL_MAPS]
    if len(maps) < 3: raise ValueError('Escolha pelo menos 3 mapas para o map pool.')
    t.map_pool = ','.join(maps)
    for field in ('bo_default', 'bo_upper_final', 'bo_lower_final', 'bo_grand_final'):
        v = int(f.get(field) or 1); setattr(t, field, v if v in (1, 3, 5) else 1)
    if max(t.bo_default, t.bo_upper_final, t.bo_lower_final, t.bo_grand_final) > len(maps):
        raise ValueError('O map pool precisa ter pelo menos tantos mapas quanto a maior série (MD3 = 3 mapas).')


@bp.route('/create', methods=['GET', 'POST'])
@admin_only
def create():
    t = Tournament(name='', max_teams=16, entry_fee_cents=0, bo_default=1, bo_upper_final=3, bo_lower_final=1, bo_grand_final=3)
    if request.method == 'POST':
        try:
            _save_form(t, request.form)
            if not t.name: raise ValueError('Dê um nome ao campeonato.')
        except ValueError as e:
            flash(str(e), 'danger'); return render_template('admin/tournaments/form.html', t=t, all_maps=ALL_MAPS, mp_enabled=payments.enabled()), 400
        db.session.add(t); db.session.commit(); flash('Campeonato criado.', 'success')
        return redirect(url_for('admin_t.registrations_view', tid=t.id))
    return render_template('admin/tournaments/form.html', t=t, all_maps=ALL_MAPS, mp_enabled=payments.enabled())


@bp.route('/<int:tid>/edit', methods=['GET', 'POST'])
@admin_only
def edit(tid):
    t = _t(tid)
    if request.method == 'POST':
        try: _save_form(t, request.form)
        except ValueError as e:
            db.session.rollback(); flash(str(e), 'danger')
            return render_template('admin/tournaments/form.html', t=t, all_maps=ALL_MAPS, mp_enabled=payments.enabled()), 400
        db.session.commit(); flash('Configurações salvas.', 'success'); return redirect(url_for('admin_t.edit', tid=t.id))
    return render_template('admin/tournaments/form.html', t=t, all_maps=ALL_MAPS, mp_enabled=payments.enabled(), tab='settings')


@bp.post('/<int:tid>/status/<status>')
@admin_only
def set_status(tid, status):
    t = _t(tid)
    if status not in STATUSES: abort(400)
    t.status = status; db.session.commit()
    return _done(f'Status alterado para: {status}', request.referrer or url_for('admin_t.registrations_view', tid=tid))


@bp.get('/<int:tid>')
@admin_only
def registrations_view(tid):
    t = _t(tid)
    regs = TournamentRegistration.query.filter_by(tournament_id=t.id).order_by(TournamentRegistration.id).all()
    for r in regs:
        p = r.latest_payment
        if p and r.status == 'AWAITING_PAYMENT': registrations.sync(p)
    db.session.commit()
    order = {'PAYMENT_REVIEW': 0, 'PENDING': 0, 'APPROVED': 1, 'AWAITING_PAYMENT': 2, 'REJECTED': 3, 'CANCELLED': 4}
    regs.sort(key=lambda r: (order.get(r.status, 5), r.seed or 999, r.id))
    return render_template('admin/tournaments/registrations.html', t=t, regs=regs, tab='registrations', slots_left=registrations.slots_left(t),
                           mp_enabled=payments.enabled(), roster_size=ROSTER_SIZE)


@bp.post('/<int:tid>/inscricoes/<int:rid>/<action>')
@admin_only
def registration_action(tid, rid, action):
    t = _t(tid); reg = db.get_or_404(TournamentRegistration, rid)
    back = url_for('admin_t.registrations_view', tid=tid)
    if reg.tournament_id != t.id: abort(404)
    if action == 'confirm':
        registrations.confirm_manual(reg, current_user, (request.form.get('note') or '').strip()[:280] or None); msg = f'{reg.team.name} confirmado.'
    elif action == 'approve': reg.status = 'APPROVED'; reg.admin_note = None; msg = f'{reg.team.name} confirmado.'
    elif action == 'reject': reg.status = 'REJECTED'; msg = f'{reg.team.name} recusado.'
    elif action == 'cancel': reg.status = 'CANCELLED'; msg = f'Inscrição de {reg.team.name} cancelada.'
    elif action == 'seed':
        v = (request.form.get('seed') or '').strip(); reg.seed = int(v) if v.isdigit() else None; msg = 'Seed atualizado.'
    elif action == 'sync':
        p = reg.latest_payment
        if p: registrations.sync(p, force=True)
        msg = 'Status consultado no Mercado Pago.'
    else: abort(400)
    db.session.commit()
    return _done(msg, back)


@bp.get('/<int:tid>/chave')
@admin_only
def bracket_admin(tid):
    t = _t(tid)
    upper, lower, final, by_id = bracket.columns(t)
    confirmed = TournamentRegistration.query.filter_by(tournament_id=t.id, status='APPROVED').all()
    return render_template('admin/tournaments/bracket.html', t=t, upper=upper, lower=lower, final=final, by_id=by_id, tab='bracket',
                           confirmed=confirmed, describe=bracket.describe_source, code=bracket.match_code,
                           size=bracket.bracket_size(len(confirmed)) if len(confirmed) >= 2 else None)


@bp.post('/<int:tid>/chave/gerar')
@admin_only
def generate(tid):
    t = _t(tid); back = url_for('admin_t.bracket_admin', tid=tid)
    regs = TournamentRegistration.query.filter_by(tournament_id=t.id, status='APPROVED').all()
    started = Match.query.filter(Match.tournament_id == t.id, Match.status.in_(('VETO', 'CONFIGURED', 'LOADED', 'LIVE'))).first() or \
        Match.query.filter(Match.tournament_id == t.id, Match.status == 'FINISHED', Match.walkover.is_(False)).first()
    if started and request.form.get('force') != '1':
        return _fail('Já existem partidas em andamento ou finalizadas. Marque "forçar" para recriar a chave do zero.', back)
    mode = request.form.get('seeding', 'random')
    if mode == 'manual': regs.sort(key=lambda r: (r.seed or 999, r.paid_at or r.created_at))
    elif mode == 'order': regs.sort(key=lambda r: (r.paid_at or r.created_at or datetime.utcnow()))
    else: random.shuffle(regs)
    for i, r in enumerate(regs, start=1): r.seed = i
    try: size = bracket.generate(t, [r.team for r in regs])
    except ValueError as e: return _fail(str(e), back)
    t.status = 'RUNNING'; db.session.commit()
    socketio.emit('bracket_update', {'tournament_id': t.id})
    return _done(f'Chave de {size} gerada com {len(regs)} times.', back)


@bp.post('/<int:tid>/chave/resetar')
@admin_only
def reset_bracket(tid):
    t = _t(tid)
    bracket.clear_bracket(t)
    for s in Server.query.filter(Server.current_match_id.isnot(None)).all():
        if not db.session.get(Match, s.current_match_id): s.current_match_id = None
    db.session.commit()
    return _done('Chave apagada.', url_for('admin_t.bracket_admin', tid=tid), 'info')


@bp.get('/partidas/<int:mid>')
@admin_only
def match_admin(mid):
    m = db.get_or_404(Match, mid)
    _, _, _, by_id = bracket.columns(m.tournament)
    return render_template('admin/tournaments/match.html', m=m, t=m.tournament, veto_state=veto.state(m, m.tournament.maps), servers=Server.query.order_by(Server.code).all(),
                           describe=bracket.describe_source, by_id=by_id, code=bracket.match_code(m), can_reopen=m.status == 'FINISHED' and bracket.can_reopen(m))


@bp.post('/partidas/<int:mid>/<action>')
@admin_only
def match_action(mid, action):
    m = db.get_or_404(Match, mid); t = m.tournament
    back = url_for('admin_t.match_admin', mid=mid)
    try:
        if action == 'veto':
            if not (m.team1_id and m.team2_id): raise ValueError('A partida ainda não tem os dois times.')
            veto.reset(m); m.status = 'VETO'; msg = 'Veto aberto: os capitães já podem banir pelo site.'
        elif action == 'veto_reset':
            veto.reset(m); msg = 'Veto zerado.'
        elif action == 'maps':
            maps = [x for x in request.form.getlist('maps') if x in t.maps]
            if len(maps) != (m.best_of or 1) or len(set(maps)) != len(maps): raise ValueError(f'Escolha {m.best_of} mapa(s) diferentes.')
            veto.reset(m); veto.set_maps(m, [(x, None) for x in maps]); msg = 'Mapas definidos sem veto.'
        elif action == 'best_of':
            if m.status not in ('WAITING', 'READY'): raise ValueError('Só dá para mudar MD1/MD3 antes do veto.')
            bo = int(request.form.get('best_of') or 1)
            if bo not in (1, 3, 5) or bo > len(t.maps): raise ValueError('Série inválida para este map pool.')
            m.best_of = bo; msg = f'Partida agora é MD{bo}.'
        elif action == 'result':
            slot = request.form.get('winner'); s1 = int(request.form.get('team1_score') or 0); s2 = int(request.form.get('team2_score') or 0)
            if slot not in ('1', '2') or not (m.team1_id and m.team2_id): raise ValueError('Escolha o vencedor.')
            if m.status == 'FINISHED': raise ValueError('Partida já finalizada. Use "Desfazer resultado" antes.')
            m.team1_score, m.team2_score = s1, s2
            bracket.finish(m, m.team1_id if slot == '1' else m.team2_id, walkover=request.form.get('walkover') == '1')
            matchzy.release_server(m); msg = 'Resultado registrado e chave atualizada.'
        elif action == 'reopen':
            bracket.reopen(m); m.team1_score = m.team2_score = 0; msg = 'Resultado desfeito.'
        elif action == 'send':
            denied = _require_pin()
            if denied: return denied
            if m.status not in ('CONFIGURED', 'LOADED'): raise ValueError('Defina os mapas (veto) antes de enviar ao servidor.')
            server = Server.query.filter_by(code=request.form.get('server') or '').first()
            if not server: raise ValueError('Escolha um servidor.')
            busy = server.current_match_id and server.current_match_id != m.id and db.session.get(Match, server.current_match_id)
            if busy and busy.status in ('LOADED', 'LIVE'): raise ValueError(f'O {server.code} está ocupado com outra partida. Libere o servidor antes.')
            for cmd in matchzy.load_commands(m, request.host_url):
                queue_command(server, 'RCON', {'command': cmd})
            server.current_match_id = m.id; m.server_id = server.code; m.status = 'LOADED'
            msg = f'Partida enviada ao {server.code}. Os jogadores já podem entrar.'
        elif action == 'release':
            denied = _require_pin()
            if denied: return denied
            server = Server.query.filter_by(code=m.server_id or '').first()
            if server:
                queue_command(server, 'RCON', {'command': 'css_endmatch'})
                if server.current_match_id == m.id: server.current_match_id = None
            if m.status in ('LOADED', 'LIVE'): m.status = 'CONFIGURED'
            msg = 'Servidor liberado (partida encerrada no servidor).'
        else: abort(400)
    except ValueError as e:
        db.session.rollback(); return _fail(str(e), back)
    db.session.commit()
    socketio.emit('match_update', {'match_id': m.id})
    return _done(msg, back)
