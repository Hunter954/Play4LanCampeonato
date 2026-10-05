from flask import Blueprint, render_template
from flask_login import login_required, current_user
from web.extensions import db
from web.models import Tournament, Match, Team, TeamMember, TournamentRegistration, User, ROSTER_SIZE
bp=Blueprint('main',__name__)

@bp.get('/')
def home():
    tournaments=Tournament.query.order_by(Tournament.id.desc()).limit(6).all()
    matches=Match.query.order_by(Match.id.desc()).limit(6).all()
    stats={'players':User.query.filter(User.steam_id64.isnot(None)).count(),'teams':Team.query.count(),'tournaments':Tournament.query.count()}
    return render_template('home.html',tournaments=tournaments,matches=matches,stats=stats,recent_teams=Team.query.order_by(Team.id.desc()).limit(8).all())

@bp.get('/conta')
@login_required
def account():
    teams=[m.team for m in current_user.memberships]
    team_ids=[t.id for t in teams]
    regs=TournamentRegistration.query.filter(TournamentRegistration.team_id.in_(team_ids or [0])).order_by(TournamentRegistration.id.desc()).all()
    open_tournaments=Tournament.query.filter_by(status='REGISTRATION').order_by(Tournament.id.desc()).all()
    has_full_team=any(len(t.members)==ROSTER_SIZE for t in teams)
    steps=[
        {'done':True,'title':'Entrar com a Steam','text':'Sua conta Steam está conectada.'},
        {'done':current_user.is_onboarded,'title':'Completar cadastro','text':'Nick, nome e contato para o dia do evento.','url':'/auth/profile','cta':'Completar'},
        {'done':bool(teams),'title':'Criar ou entrar num time','text':'Crie um time ou peça o link de convite ao seu capitão.','url':'/teams/create','cta':'Criar time'},
        {'done':has_full_team,'title':f'Fechar o elenco ({ROSTER_SIZE} jogadores)','text':'Envie o link de convite para completar o time.','url':f'/teams/{teams[0].id}' if teams else None,'cta':'Convidar'},
        {'done':any(r.status!='REJECTED' for r in regs),'title':'Inscrever no campeonato','text':'O capitão inscreve o time num campeonato aberto.','url':f'/tournaments/{open_tournaments[0].id}' if open_tournaments else '/tournaments/','cta':'Ver campeonatos'},
    ]
    return render_template('account.html',teams=teams,regs=regs,open_tournaments=open_tournaments,steps=steps,roster_size=ROSTER_SIZE)

@bp.get('/jogadores/<int:uid>')
def player(uid):
    u=db.get_or_404(User,uid)
    if not u.steam_id64: return render_template('errors/404.html'),404
    teams=[m.team for m in u.memberships]
    return render_template('players/detail.html',player=u,teams=teams)
