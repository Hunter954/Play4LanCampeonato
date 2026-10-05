import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test'
os.environ['AGENT_SHARED_TOKEN'] = 'agent-test'
import random
from datetime import datetime
import pytest
from flask import g
from werkzeug.security import generate_password_hash
from web.app import create_app
from web.extensions import db
from web.models import (User, Team, TeamMember, Tournament, TournamentRegistration, Match, MatchMap, Payment,
                        PlayerMapStat, Server, ServerCommand, AdminSetting, VetoAction)
from web import bracket, veto, stats


@pytest.fixture
def app():
    app = create_app(); app.config['TESTING'] = True
    @app.before_request
    def _forget_login_user(): g.pop('_login_user', None)
    with app.app_context():
        yield app
        db.session.remove(); db.drop_all()


_n = [0]
def user(onboarded=True, admin=False):
    _n[0] += 1; n = _n[0]
    u = User(steam_id64=str(76561198000000000 + n), steam_name=f's{n}', is_admin=admin)
    if onboarded: u.nickname = f'p{n}'; u.real_name = f'Jogador Teste{n}'; u.onboarded_at = datetime.utcnow()
    db.session.add(u); db.session.commit(); return u


def team(name=None, size=5):
    members = [user() for _ in range(size)]
    t = Team(name=name or f'Time {members[0].id}', tag=f'T{members[0].id}'[:5], owner_id=members[0].id); db.session.add(t); db.session.flush()
    for i, m in enumerate(members): db.session.add(TeamMember(team_id=t.id, user_id=m.id, role='OWNER' if i == 0 else 'PLAYER'))
    db.session.commit(); return t


def client_as(app, u):
    c = app.test_client()
    with c.session_transaction() as s: s['_user_id'] = str(u.id); s['_fresh'] = True
    return c


def tournament(**kw):
    t = Tournament(name='Copa', max_teams=kw.pop('max_teams', 16), entry_fee_cents=kw.pop('fee', 0), bo_default=1, bo_upper_final=3, bo_lower_final=1, bo_grand_final=3, **kw)
    db.session.add(t); db.session.commit(); return t


def play_all(t, pick=lambda m: m.team1_id):
    """Joga a chave inteira escolhendo o vencedor com `pick`; devolve a lista de confrontos na ordem."""
    history = []
    for _ in range(200):
        ready = Match.query.filter_by(tournament_id=t.id, status='READY').order_by(Match.id).all()
        if not ready: break
        for m in ready:
            history.append((m.bracket, m.round, {m.team1_id, m.team2_id}))
            bracket.finish(m, pick(m))
        db.session.flush()
    return history


# ---------------- Chaveamento ----------------

def test_seed_order_standard():
    assert bracket.seed_order(16) == [1, 16, 8, 9, 4, 13, 5, 12, 2, 15, 7, 10, 3, 14, 6, 11]


def test_double_elim_16_full_run_and_no_immediate_rematch(app):
    t = tournament(); teams = [team() for _ in range(16)]
    assert bracket.generate(t, teams) == 16
    ms = Match.query.filter_by(tournament_id=t.id).all()
    assert len(ms) == 30
    assert sum(1 for m in ms if m.bracket == 'UPPER') == 15 and sum(1 for m in ms if m.bracket == 'LOWER') == 14
    assert Match.query.filter_by(tournament_id=t.id, bracket='UPPER', round=4).one().best_of == 3   # final da upper MD3
    assert Match.query.filter_by(tournament_id=t.id, bracket='LOWER', round=6).one().best_of == 1   # final da lower MD1
    assert t.grand_final.best_of == 3
    random.seed(7)
    history = play_all(t, pick=lambda m: random.choice([m.team1_id, m.team2_id]))
    assert all(m.status == 'FINISHED' for m in Match.query.filter_by(tournament_id=t.id))
    assert t.champion is not None
    # cada time perde no máximo 2 vezes; o campeão no máximo 1
    losses = {}
    for m in Match.query.filter_by(tournament_id=t.id):
        losses[m.loser_id] = losses.get(m.loser_id, 0) + 1
    assert max(losses.values()) <= 2 and losses.get(t.champion.id, 0) <= 1
    # quem cai da upper na 2ª rodada não reencontra na lower quem já enfrentou
    met = []
    for br, rnd, pair in history:
        if br == 'LOWER' and rnd == 2: assert pair not in met
        met.append(pair)


def test_byes_with_13_teams(app):
    t = tournament(); teams = [team() for _ in range(13)]
    bracket.generate(t, teams)
    walkovers = Match.query.filter_by(tournament_id=t.id, bracket='UPPER', round=1, walkover=True).all()
    assert len(walkovers) == 3 and {m.winner_id for m in walkovers} == {teams[0].id, teams[1].id, teams[2].id}  # seeds 1-3 avançam
    play_all(t)
    assert t.champion is not None


def test_reopen_result(app):
    t = tournament(); bracket.generate(t, [team() for _ in range(4)])
    m = Match.query.filter_by(tournament_id=t.id, bracket='UPPER', round=1, position=0).one()
    bracket.finish(m, m.team2_id); db.session.flush()
    nxt = db.session.get(Match, m.next_match_id)
    assert m.team2_id in (nxt.team1_id, nxt.team2_id)
    bracket.reopen(m)
    assert nxt.team1_id is None and m.status == 'READY'


# ---------------- Veto ----------------

def test_veto_plans():
    assert veto.plan(1, 7) == [(1, 'ban'), (2, 'ban')] * 3
    assert [a for _, a in veto.plan(3, 7)] == ['ban', 'ban', 'pick', 'pick', 'ban', 'ban']


def test_veto_flow_bo1(app):
    t = tournament(); bracket.generate(t, [team() for _ in range(4)])
    m = Match.query.filter_by(tournament_id=t.id, status='READY').first(); m.status = 'VETO'
    pool = t.maps
    with pytest.raises(ValueError): veto.apply(m, pool, m.team2_id, pool[0])  # não é a vez do time 2
    for i, name in enumerate(pool[:6]):
        veto.apply(m, pool, m.team1_id if i % 2 == 0 else m.team2_id, name)
    assert m.status == 'CONFIGURED' and [mm.map_name for mm in m.maps_played] == [pool[6]]


def test_captain_veto_endpoint(app):
    t = tournament(); bracket.generate(t, [team() for _ in range(4)])
    m = Match.query.filter_by(tournament_id=t.id, status='READY').first(); m.status = 'VETO'; db.session.commit()
    cap1, cap2 = m.team1.owner, m.team2.owner
    assert client_as(app, cap2).post(f'/partidas/{m.id}/veto', json={'map': 'Nuke'}).status_code == 409
    r = client_as(app, cap1).post(f'/partidas/{m.id}/veto', json={'map': 'Nuke'})
    assert r.status_code == 200 and r.get_json()['state']['veto']['next']['slot'] == 2
    assert app.test_client().get(f'/partidas/{m.id}').status_code == 200


# ---------------- Pagamento (Mercado Pago simulado) ----------------

class FakeResp:
    def __init__(self, data, code=201): self._d = data; self.status_code = code; self.content = b'x'
    def json(self): return self._d


def test_paid_registration_flow_with_mercadopago(app, monkeypatch):
    monkeypatch.setenv('MP_ACCESS_TOKEN', 'TEST-token')
    t = tournament(fee=5000, max_teams=2); tm = team(); cap = tm.owner
    sent = {}
    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(json); return FakeResp({'id': 999, 'status': 'pending', 'date_of_expiration': '2099-01-01T00:00:00.000-03:00',
                                            'point_of_interaction': {'transaction_data': {'qr_code': '000201PIX', 'qr_code_base64': 'iVBOR'}}})
    monkeypatch.setattr('web.payments.requests.post', fake_post)
    c = client_as(app, cap)
    r = c.post(f'/tournaments/{t.id}/register/{tm.id}')
    assert r.status_code == 302 and f'/inscricao/{tm.id}' in r.location
    reg = TournamentRegistration.query.one(); assert reg.status == 'AWAITING_PAYMENT'
    c.post(f'/tournaments/{t.id}/inscricao/{tm.id}/pix', data={'email': 'cap@ex.com'})
    p = Payment.query.one()
    assert p.provider_payment_id == '999' and p.qr_code == '000201PIX' and sent['transaction_amount'] == 50.0 and sent['payment_method_id'] == 'pix'
    assert b'000201PIX' in c.get(f'/tournaments/{t.id}/inscricao/{tm.id}').data
    # elenco travado enquanto a inscrição está ativa
    player = [m.user for m in tm.members if m.user_id != cap.id][0]
    client_as(app, player).post(f'/teams/{tm.id}/leave'); assert len(db.session.get(Team, tm.id).members) == 5
    # webhook: status é reconsultado na API
    monkeypatch.setattr('web.payments.requests.get', lambda *a, **k: FakeResp({'id': 999, 'status': 'approved'}, 200))
    assert app.test_client().post('/api/v1/payments/mercadopago/webhook?data.id=999&type=payment', json={'type': 'payment', 'data': {'id': '999'}}).status_code == 200
    db.session.refresh(reg)
    assert reg.status == 'APPROVED' and reg.paid_at and c.get(f'/tournaments/{t.id}/inscricao/{tm.id}/status').get_json()['status'] == 'APPROVED'


def test_open_pix_reserves_last_slot(app, monkeypatch):
    monkeypatch.setenv('MP_ACCESS_TOKEN', 'TEST-token')
    monkeypatch.setattr('web.payments.requests.post', lambda *a, **k: FakeResp({'id': 1, 'status': 'pending', 'date_of_expiration': '2099-01-01T00:00:00.000Z', 'point_of_interaction': {'transaction_data': {'qr_code': 'x'}}}))
    t = tournament(fee=1000, max_teams=1); a, b = team(), team()
    client_as(app, a.owner).post(f'/tournaments/{t.id}/register/{a.id}')
    client_as(app, a.owner).post(f'/tournaments/{t.id}/inscricao/{a.id}/pix', data={'email': 'a@ex.com'})
    from web import registrations
    assert any('vagas' in p for p in registrations.problems(t, b))


def test_webhook_signature(monkeypatch):
    import hmac, hashlib
    from web import payments
    monkeypatch.setenv('MP_WEBHOOK_SECRET', 'segredo')
    sig = hmac.new(b'segredo', b'id:123;request-id:abc;ts:1700;', hashlib.sha256).hexdigest()
    assert payments.valid_signature(f'ts=1700,v1={sig}', 'abc', '123')
    assert not payments.valid_signature('ts=1700,v1=errado', 'abc', '123')


# ---------------- Servidor: MatchZy e telemetria ----------------

def _configured_match(t):
    bracket.generate(t, [team() for _ in range(4)])
    m = Match.query.filter_by(tournament_id=t.id, status='READY').order_by(Match.id).first()
    veto.set_maps(m, [('Mirage', None)]); db.session.commit(); return m


def _stats_team(team_obj, kills):
    return {'id': str(team_obj.id), 'name': team_obj.name, 'score': 13 if kills > 10 else 7,
            'players': [{'steamid': m.user.steam_id64, 'name': m.user.display_name,
                         'stats': {'kills': kills, 'deaths': 10, 'assists': 3, 'damage': kills * 90, 'headshot_kills': kills // 2,
                                   'rounds_played': 20, 'kast': 15, '1k': 5, '2k': 2, '3k': 1, 'first_kills_t': 2, '1v1': 1}} for m in team_obj.members]}


def test_matchzy_config_events_and_bracket_advance(app):
    t = tournament(); m = _configured_match(t); c = app.test_client()
    assert c.get(f'/api/v1/matches/{m.id}/config?token=errado').status_code == 403
    cfg = c.get(f'/api/v1/matches/{m.id}/config?token={m.config_token}').get_json()
    assert cfg['maplist'] == ['de_mirage'] and len(cfg['team1']['players']) == 5 and cfg['map_sides'] == ['knife'] and cfg['matchid'] == m.id
    url = f'/api/v1/matchzy/events?token={m.config_token}'
    c.post(url, json={'event': 'going_live', 'matchid': m.id, 'map_number': 0})
    assert db.session.get(Match, m.id).status == 'LIVE'
    c.post(url, json={'event': 'round_end', 'matchid': m.id, 'map_number': 0, 'round_number': 20,
                      'team1': _stats_team(m.team1, 18), 'team2': _stats_team(m.team2, 9)})
    assert PlayerMapStat.query.filter_by(match_id=m.id).count() == 10
    row = PlayerMapStat.query.filter_by(match_id=m.id, team_id=m.team1_id).first()
    assert row.headshot_kills == 9 and row.k2 == 2 and row.first_kills == 2 and row.clutches_won == 1
    assert db.session.get(Match, m.id).team1_score == 13
    c.post(url, json={'event': 'series_end', 'matchid': m.id, 'winner': {'side': '3', 'team': 'team1'}, 'team1_series_score': 1, 'team2_series_score': 0})
    m = db.session.get(Match, m.id)
    assert m.status == 'FINISHED' and m.winner_id == m.team1_id
    assert m.team1_id in (db.session.get(Match, m.next_match_id).team1_id, db.session.get(Match, m.next_match_id).team2_id)
    board = stats.leaderboard(t); assert board[0]['rating'] and board[0]['hs_pct'] == 50
    for url2 in [f'/partidas/{m.id}', f'/tournaments/{t.id}/estatisticas', f'/jogadores/{row.user_id}', f'/tournaments/{t.id}/chave', f'/tournaments/{t.id}/partidas']:
        assert c.get(url2).status_code == 200, url2


def test_telemetry_fallback_from_heartbeat(app):
    t = tournament(); m = _configured_match(t); m.status = 'LOADED'
    s = Server(code='server01', host_id='LAN', current_match_id=m.id); db.session.add(s); db.session.commit()
    players = [{'steam_id64': mb.user.steam_id64, 'name': 'x', 'kills': 7, 'deaths': 3, 'assists': 1, 'damage': 700} for mb in m.team1.members]
    r = app.test_client().post('/api/v1/agent/heartbeat', headers={'Authorization': 'Bearer agent-test'},
                               json={'host_id': 'LAN', 'servers': [{'code': 'server01', 'status': 'ONLINE', 'telemetry': {'players': players, 'team1_score': 5, 'team2_score': 3}}]})
    assert r.status_code == 200
    assert PlayerMapStat.query.filter_by(match_id=m.id, source='telemetry').count() == 5
    assert db.session.get(Match, m.id).status == 'LIVE' and db.session.get(Match, m.id).team1_score == 5


# ---------------- Servidores: status real e atualização ----------------

def _hb(app, version=None, status='ONLINE', players=0):
    tel = {'players': [{'steam_id64': '1', 'name': 'x'}] * players, 'player_count': players}
    if version: tel['version'] = version
    return app.test_client().post('/api/v1/agent/heartbeat', headers={'Authorization': 'Bearer agent-test'},
                                  json={'host_id': 'LAN', 'agent_version': '1.1.0', 'servers': [{'code': 'SERVER01', 'status': status, 'telemetry': tel}]})


def test_heartbeat_version_settings_and_stale_status(app):
    from datetime import timedelta
    r = _hb(app, {'installed': '1.41.7.8', 'required': '1.41.8.8', 'up_to_date': False, 'checked_at': 1791242951})
    assert r.get_json()['settings'] == {'SERVER01': {'auto_update': True, 'busy': False}}
    s = Server.query.one()
    assert s.installed_version == '1.41.7.8' and s.needs_update and s.agent_version == '1.1.0' and s.live_status == 'ONLINE'
    s.last_heartbeat -= timedelta(seconds=60); db.session.commit()
    assert db.session.get(Server, s.id).live_status == 'NO_SIGNAL'   # Agent parou: não mostra mais "online"


def test_update_command_and_auto_update_toggle(app):
    admin = user(admin=True); c = client_as(app, admin)
    db.session.add(AdminSetting(key='admin_action_pin_hash', value=generate_password_hash('1234'))); db.session.commit()
    _hb(app, {'installed': '1.41.7.8', 'required': '1.41.8.8', 'up_to_date': False})
    ajax = {'X-Requested-With': 'XMLHttpRequest'}
    assert c.post('/admin/servers/SERVER01/UPDATE', data={'pin': '1234'}, headers=ajax).status_code == 202
    assert ServerCommand.query.filter_by(command='UPDATE').count() == 1
    # partida rodando bloqueia a atualização
    t = tournament(); m = _configured_match(t); m.status = 'LIVE'; Server.query.one().current_match_id = m.id; db.session.commit()
    assert c.post('/admin/servers/SERVER01/UPDATE', data={'pin': '1234'}, headers=ajax).status_code == 409
    assert _hb(app).get_json()['settings']['SERVER01']['busy'] is True
    c.post('/admin/servers/SERVER01/auto-update', data={'enabled': '0'}, headers=ajax)
    assert Server.query.one().auto_update is False and _hb(app).get_json()['settings']['SERVER01']['auto_update'] is False
    for url in ['/admin/', '/admin/servers/', '/admin/servers/SERVER01', '/admin/servers/SERVER01/players', '/admin/servers/SERVER01/match',
                '/admin/servers/SERVER01/chat', '/admin/servers/SERVER01/backups', '/admin/servers/SERVER01/logs', '/admin/jogadores', '/admin/seguranca']:
        assert c.get(url).status_code == 200, url


def test_toggle_admin_needs_pin(app):
    admin = user(admin=True); other = user(); c = client_as(app, admin)
    db.session.add(AdminSetting(key='admin_action_pin_hash', value=generate_password_hash('1234'))); db.session.commit()
    ajax = {'X-Requested-With': 'XMLHttpRequest'}
    assert c.post(f'/admin/jogadores/{other.id}/admin', data={'pin': '9999'}, headers=ajax).status_code == 403
    assert c.post(f'/admin/jogadores/{other.id}/admin', data={'pin': '1234'}, headers=ajax).get_json()['ok']
    assert db.session.get(User, other.id).is_admin
    assert b'Remover admin' in c.get('/admin/jogadores').data
    assert client_as(app, other).get('/admin/').status_code == 200


def test_agent_auto_update_rules():
    from agent.cs2 import CS2Process
    p = CS2Process({'exe': 'C:/x/runtime/server01/game/bin/win64/cs2.exe', 'args': []}, {'auto_update': True})
    assert p.install_dir.replace('\\', '/').endswith('runtime/server01')
    started = []
    p.start_update = lambda trigger='manual': started.append(trigger)
    p.version['up_to_date'] = False
    assert not p.maybe_auto_update(player_count=3, busy=False)   # com gente jogando não atualiza
    assert not p.maybe_auto_update(player_count=0, busy=True)    # partida em andamento não atualiza
    assert p.maybe_auto_update(player_count=0, busy=False) and started == ['auto']
    p.auto_update = False; assert not p.maybe_auto_update(0, False)


# ---------------- Admin ----------------

def test_admin_full_day_flow(app):
    admin = user(admin=True); c = client_as(app, admin)
    db.session.add(AdminSetting(key='admin_action_pin_hash', value=generate_password_hash('1234'))); db.session.add(Server(code='server01', host_id='LAN', status='ONLINE')); db.session.commit()
    assert c.get('/admin/tournaments/create').status_code == 200
    r = c.post('/admin/tournaments/create', data={'name': 'Copa LAN', 'max_teams': '16', 'entry_fee': '50,00', 'maps': ['Mirage', 'Inferno', 'Nuke', 'Ancient', 'Anubis', 'Dust II', 'Train'],
                                                  'bo_default': '1', 'bo_upper_final': '3', 'bo_lower_final': '1', 'bo_grand_final': '3', 'starts_at': '2026-11-01T14:00'})
    t = Tournament.query.filter_by(name='Copa LAN').one(); assert t.entry_fee_cents == 5000 and r.status_code == 302
    teams = [team() for _ in range(6)]
    for tm in teams: db.session.add(TournamentRegistration(tournament_id=t.id, team_id=tm.id, status='AWAITING_PAYMENT'))
    db.session.commit()
    for reg in TournamentRegistration.query.filter_by(tournament_id=t.id):
        assert c.post(f'/admin/tournaments/{t.id}/inscricoes/{reg.id}/confirm', headers={'X-Requested-With': 'XMLHttpRequest'}).get_json()['ok']
    assert t.approved_count == 6
    for url in [f'/admin/tournaments/{t.id}', f'/admin/tournaments/{t.id}/chave', f'/admin/tournaments/{t.id}/edit', '/admin/tournaments/', '/admin/']:
        assert c.get(url).status_code == 200, url
    c.post(f'/admin/tournaments/{t.id}/chave/gerar', data={'seeding': 'random'})
    assert Match.query.filter_by(tournament_id=t.id).count() == 14  # chave de 8
    m = Match.query.filter_by(tournament_id=t.id, status='READY').first()
    assert c.get(f'/admin/tournaments/partidas/{m.id}').status_code == 200
    c.post(f'/admin/tournaments/partidas/{m.id}/veto'); assert db.session.get(Match, m.id).status == 'VETO'
    c.post(f'/admin/tournaments/partidas/{m.id}/maps', data={'maps': ['Inferno']}); assert db.session.get(Match, m.id).current_map == 'Inferno'
    assert c.post(f'/admin/tournaments/partidas/{m.id}/send', data={'server': 'server01', 'pin': '0000'}, headers={'X-Requested-With': 'XMLHttpRequest'}).status_code == 403
    c.post(f'/admin/tournaments/partidas/{m.id}/send', data={'server': 'server01', 'pin': '1234'})
    cmds = [x.payload['command'] for x in ServerCommand.query.order_by(ServerCommand.id)]
    assert cmds[0].startswith('matchzy_loadmatch_url') and cmds[1].startswith('matchzy_remote_log_url') and db.session.get(Match, m.id).status == 'LOADED'
    c.post(f'/admin/tournaments/partidas/{m.id}/result', data={'winner': '2', 'team1_score': '0', 'team2_score': '1', 'walkover': '1'})
    m = db.session.get(Match, m.id)
    assert m.status == 'FINISHED' and m.winner_id == m.team2_id and Server.query.one().current_match_id is None
