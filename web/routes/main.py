from flask import Blueprint, render_template
from flask_login import login_required, current_user
from web.extensions import db
from web.models import Tournament, Match, Team, TournamentRegistration, User, ROSTER_SIZE, ACTIVE_REG_STATUSES
from web import stats
bp=Blueprint('main',__name__)

@bp.get('/')
def home():
    tournaments=Tournament.query.order_by(Tournament.id.desc()).limit(6).all()
    live=Match.query.filter(Match.status.in_(('LIVE','LOADED'))).order_by(Match.id).all()
    recent=Match.query.filter_by(status='FINISHED',walkover=False).order_by(Match.finished_at.desc().nullslast(),Match.id.desc()).limit(6).all()
    stats_={'players':User.query.filter(User.steam_id64.isnot(None)).count(),'teams':Team.query.count(),'tournaments':Tournament.query.count()}
    return render_template('home.html',tournaments=tournaments,live=live,matches=recent,stats=stats_,recent_teams=Team.query.order_by(Team.id.desc()).limit(8).all())

@bp.get('/conta')
@login_required
def account():
    teams=[m.team for m in current_user.memberships]
    team_ids=[t.id for t in teams]
    regs=TournamentRegistration.query.filter(TournamentRegistration.team_id.in_(team_ids or [0]),TournamentRegistration.status.in_(ACTIVE_REG_STATUSES)).order_by(TournamentRegistration.id.desc()).all()
    open_tournaments=Tournament.query.filter_by(status='REGISTRATION').order_by(Tournament.id.desc()).all()
    full_team=next((t for t in teams if len(t.members)==ROSTER_SIZE),None)
    pending_pay=next((r for r in regs if r.status=='AWAITING_PAYMENT'),None)
    target=open_tournaments[0] if open_tournaments else None
    steps=[
        {'done':True,'title':'Entrar com a Steam','text':'Sua conta Steam está conectada.'},
        {'done':current_user.is_onboarded,'title':'Completar cadastro','text':'Nick, nome e contato para o dia do evento.','url':'/auth/profile','cta':'Completar'},
        {'done':bool(teams),'title':'Criar ou entrar num time','text':'Crie um time ou peça o link de convite ao seu capitão.','url':'/teams/create','cta':'Criar time'},
        {'done':bool(full_team),'title':f'Fechar o elenco ({ROSTER_SIZE} jogadores)','text':'Envie o link de convite. Com 5 jogadores, o pagamento é liberado.','url':f'/teams/{teams[0].id}' if teams else None,'cta':'Convidar'},
        {'done':any(r.status=='APPROVED' for r in regs),'title':'Pagar e confirmar a vaga','text':'O capitão paga a inscrição via Pix e a vaga é confirmada na hora.',
         'url':f'/tournaments/{pending_pay.tournament_id}/inscricao/{pending_pay.team_id}' if pending_pay else (f'/tournaments/{target.id}' if target else '/tournaments/'),
         'cta':'Pagar Pix' if pending_pay else 'Ver campeonatos'},
    ]
    upcoming=[]
    if team_ids:
        upcoming=Match.query.filter(db.or_(Match.team1_id.in_(team_ids),Match.team2_id.in_(team_ids)),Match.status!='FINISHED').order_by(Match.id).limit(5).all()
    return render_template('account.html',teams=teams,regs=regs,open_tournaments=open_tournaments,steps=steps,roster_size=ROSTER_SIZE,upcoming=upcoming)

@bp.get('/jogadores/<int:uid>')
def player(uid):
    u=db.get_or_404(User,uid)
    if not u.steam_id64: return render_template('errors/404.html'),404
    teams=[m.team for m in u.memberships]
    career,recent=stats.player_career(u)
    return render_template('players/detail.html',player=u,teams=teams,career=career,recent=recent)
