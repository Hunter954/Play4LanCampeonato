import os
os.environ['DATABASE_URL']='sqlite:///:memory:'
os.environ['SECRET_KEY']='test'
os.environ.pop('STEAM_API_KEY',None)
from datetime import datetime
import pytest
from flask import g
from web.app import create_app
from web.extensions import db
from web.models import User, Team, TeamMember, Invite, Tournament, TournamentRegistration


@pytest.fixture
def app():
    app=create_app(); app.config['TESTING']=True
    # O contexto fica aberto durante o teste; sem isso o Flask-Login reaproveitaria o usuário da requisição anterior.
    @app.before_request
    def _forget_login_user(): g.pop('_login_user', None)
    with app.app_context():
        yield app
        db.session.remove(); db.drop_all()


def make_user(n, onboarded=True):
    u=User(steam_id64=str(76561198000000000+n), steam_name=f'steam{n}')
    if onboarded: u.nickname=f'player{n}'; u.real_name=f'Jogador Numero{n}'; u.onboarded_at=datetime.utcnow()
    db.session.add(u); db.session.commit(); return u


def client_as(app, user):
    c=app.test_client()
    with c.session_transaction() as s: s['_user_id']=str(user.id); s['_fresh']=True
    return c


def test_public_pages_render(app):
    c=app.test_client()
    for url in ['/', '/teams/', '/tournaments/', '/auth/entrar']:
        r=c.get(url); assert r.status_code==200, url; assert b'site.css' in r.data
    assert c.get('/nao-existe').status_code==404
    assert c.get('/conta').status_code==302


def test_steam_callback_sends_new_player_to_onboarding(app, monkeypatch):
    class Resp: text='ns:http://specs.openid.net/auth/2.0\nis_valid:true\n'
    monkeypatch.setattr('web.routes.auth.requests.post', lambda *a, **k: Resp())
    c=app.test_client()
    with c.session_transaction() as s: s['post_steam_next']='/teams/invite/abc'
    r=c.get('/auth/steam/callback?openid.claimed_id=https://steamcommunity.com/openid/id/76561198000000999')
    assert r.status_code==302 and '/auth/profile' in r.location and 'invite' in r.location
    assert User.query.filter_by(steam_id64='76561198000000999').one().last_login_at


def test_steam_next_rejects_external_urls(app):
    r=app.test_client().get('/auth/steam?next=//evil.com')
    assert r.status_code==302
    with app.test_client() as c:
        c.get('/auth/steam?next=https://evil.com');
        with c.session_transaction() as s: assert s.get('post_steam_next') is None


def test_steam_login_behind_railway_proxy_uses_https_and_matching_realm(app, monkeypatch):
    from urllib.parse import urlparse, parse_qs
    monkeypatch.setenv('STEAM_REALM','https://camp.play4lan.com.br')  # domínio diferente do acessado
    r=app.test_client().get('/auth/steam', headers={'X-Forwarded-Proto':'https','X-Forwarded-Host':'web-production-9c99d.up.railway.app'})
    q=parse_qs(urlparse(r.location).query)
    assert q['openid.return_to']==['https://web-production-9c99d.up.railway.app/auth/steam/callback']
    assert q['openid.realm']==['https://web-production-9c99d.up.railway.app']
    monkeypatch.setenv('STEAM_REALM','https://web-production-9c99d.up.railway.app')
    r=app.test_client().get('/auth/steam', headers={'X-Forwarded-Proto':'https','X-Forwarded-Host':'web-production-9c99d.up.railway.app'})
    assert parse_qs(urlparse(r.location).query)['openid.realm']==['https://web-production-9c99d.up.railway.app']


def test_onboarding_required_and_profile_validation(app):
    u=make_user(1, onboarded=False); c=client_as(app,u)
    assert '/auth/profile' in c.get('/teams/create').location
    r=c.post('/auth/profile', data={'nickname':'x','real_name':'Fulano'})
    assert r.status_code==400 and not db.session.get(User,u.id).is_onboarded
    r=c.post('/auth/profile?next=/teams/create', data={'nickname':'Fulano','real_name':'Fulano de Tal','whatsapp':'(45) 99999-0000'})
    assert r.status_code==302 and r.location.endswith('/teams/create')
    assert db.session.get(User,u.id).is_onboarded


def test_team_flow_invite_full_roster_and_registration(app):
    cap=make_user(1); c=client_as(app,cap)
    r=c.post('/teams/create', data={'name':'Furia da Fronteira','tag':'fdf'})
    team=Team.query.one(); assert r.status_code==302 and team.tag=='FDF' and team.owner_id==cap.id
    assert c.post('/teams/create', data={'name':'furia da fronteira','tag':'XYZ'}).status_code==400
    assert c.post('/teams/create', data={'name':'Outro','tag':'F D'}).status_code==400

    token=Invite.query.filter_by(team_id=team.id,active=True).one().token
    assert app.test_client().get(f'/teams/invite/{token}').status_code==200
    for n in range(2,6):
        p=make_user(n); r=client_as(app,p).post(f'/teams/invite/{token}/accept'); assert r.status_code==302
    assert len(db.session.get(Team,team.id).members)==5
    extra=make_user(6); client_as(app,extra).post(f'/teams/invite/{token}/accept')
    assert len(db.session.get(Team,team.id).members)==5

    t=Tournament(name='Copa LAN',max_teams=8); db.session.add(t); db.session.commit()
    assert c.get(f'/tournaments/{t.id}').status_code==200
    r=c.post(f'/tournaments/{t.id}/register/{team.id}')
    assert TournamentRegistration.query.filter_by(tournament_id=t.id,team_id=team.id).one().status=='PENDING'

    # jogador do time inscrito não pode ser inscrito por outro time
    p2=User.query.filter_by(nickname='player2').one(); cap2=make_user(7)
    t2=Team(name='Rival',tag='RVL',owner_id=cap2.id); db.session.add(t2); db.session.flush()
    for u in [cap2,p2]+[make_user(n) for n in (8,9,10)]: db.session.add(TeamMember(team_id=t2.id,user_id=u.id))
    db.session.commit()
    client_as(app,cap2).post(f'/tournaments/{t.id}/register/{t2.id}')
    assert TournamentRegistration.query.filter_by(team_id=t2.id).count()==0

    # time inscrito não pode ser excluído; outro jogador não gerencia
    client_as(app,cap).post(f'/teams/{team.id}/delete'); assert db.session.get(Team,team.id)
    assert client_as(app,p2).post(f'/teams/{team.id}/remove/{cap.id}').status_code==403


def test_captain_transfer_leave_and_delete(app):
    cap=make_user(1); p=make_user(2); c=client_as(app,cap)
    c.post('/teams/create', data={'name':'Time Teste','tag':'TT'}); team=Team.query.one()
    db.session.add(TeamMember(team_id=team.id,user_id=p.id)); db.session.commit()
    assert c.post(f'/teams/{team.id}/leave').status_code==302 and team.has_member(cap)  # capitão não sai
    c.post(f'/teams/{team.id}/captain/{p.id}'); db.session.refresh(team)
    assert team.owner_id==p.id
    c.post(f'/teams/{team.id}/leave'); db.session.refresh(team)
    assert not team.has_member(cap)
    client_as(app,p).post(f'/teams/{team.id}/delete')
    assert Team.query.count()==0 and Invite.query.count()==0


def test_account_and_player_pages(app):
    u=make_user(1); c=client_as(app,u)
    c.post('/teams/create', data={'name':'Time Conta','tag':'TC'})
    for url in ['/conta', f'/jogadores/{u.id}', '/auth/profile', f'/teams/{Team.query.one().id}', f'/teams/{Team.query.one().id}/edit']:
        assert c.get(url).status_code==200, url


def test_adds_missing_columns_to_existing_database(tmp_path):
    os.environ['DATABASE_URL']=f'sqlite:///{tmp_path}/old.db'
    try:
        app=create_app()
        with app.app_context():
            db.session.execute(db.text('ALTER TABLE "user" DROP COLUMN whatsapp')); db.session.commit()
        app=create_app()
        with app.app_context():
            cols={c['name'] for c in db.inspect(db.engine).get_columns('user')}
            assert 'whatsapp' in cols
    finally:
        os.environ['DATABASE_URL']='sqlite:///:memory:'
