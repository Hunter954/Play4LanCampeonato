from flask import Blueprint, render_template, redirect, url_for, abort, flash
from flask_login import login_required, current_user
from web.extensions import db
from web.models import Tournament, TournamentRegistration, Team, TeamMember, Match, ROSTER_SIZE
from web.routes.auth import onboarded_required
bp=Blueprint('tournaments',__name__,url_prefix='/tournaments')

def registration_problems(t, team):
    """Lista o que impede o time de se inscrever (vazia = pode inscrever)."""
    problems=[]
    if not t.is_open: problems.append('As inscrições deste campeonato estão fechadas.')
    if len(team.members)!=ROSTER_SIZE: problems.append(f'O time precisa ter exatamente {ROSTER_SIZE} jogadores (hoje tem {len(team.members)}).')
    pending=[m.user.display_name for m in team.members if not m.user.is_onboarded]
    if pending: problems.append('Jogadores sem cadastro completo: '+', '.join(pending)+'.')
    others=(TeamMember.query.join(TournamentRegistration,TournamentRegistration.team_id==TeamMember.team_id)
            .filter(TournamentRegistration.tournament_id==t.id,TournamentRegistration.status!='REJECTED',TeamMember.team_id!=team.id,
                    TeamMember.user_id.in_([m.user_id for m in team.members] or [0])).all())
    if others: problems.append('Já inscritos por outro time: '+', '.join(sorted({o.user.display_name for o in others}))+'.')
    if t.approved_count>=t.max_teams: problems.append('Todas as vagas já foram preenchidas.')
    return problems

@bp.get('/')
def index():
    return render_template('tournaments/index.html',tournaments=Tournament.query.order_by(Tournament.id.desc()).all())

@bp.get('/<int:tid>')
def detail(tid):
    t=Tournament.query.get_or_404(tid)
    regs=TournamentRegistration.query.filter(TournamentRegistration.tournament_id==tid,TournamentRegistration.status!='REJECTED').order_by(TournamentRegistration.id).all()
    registered_ids={r.team_id for r in regs}
    my_teams=[]
    if current_user.is_authenticated:
        for team in Team.query.filter(Team.owner_id==current_user.id).order_by(Team.name).all():
            my_teams.append({'team':team,'registered':team.id in registered_ids,'problems':[] if team.id in registered_ids else registration_problems(t,team)})
    matches=Match.query.filter_by(tournament_id=tid).order_by(Match.id.desc()).limit(20).all()
    return render_template('tournaments/detail.html',t=t,regs=regs,my_teams=my_teams,matches=matches,roster_size=ROSTER_SIZE)

@bp.post('/<int:tid>/register/<int:team_id>')
@onboarded_required
def register(tid,team_id):
    t=Tournament.query.get_or_404(tid); team=Team.query.get_or_404(team_id)
    if not (current_user.is_admin or team.owner_id==current_user.id): abort(403)
    if TournamentRegistration.query.filter_by(tournament_id=tid,team_id=team_id).filter(TournamentRegistration.status!='REJECTED').first():
        return redirect(url_for('tournaments.detail',tid=tid))
    problems=registration_problems(t,team)
    if problems:
        for p in problems: flash(p,'danger')
        return redirect(url_for('tournaments.detail',tid=tid))
    old=TournamentRegistration.query.filter_by(tournament_id=tid,team_id=team_id).first()
    if old: old.status='PENDING'
    else: db.session.add(TournamentRegistration(tournament_id=tid,team_id=team_id))
    db.session.commit(); flash(f'{team.name} inscrito! Aguarde a confirmação da organização.','success')
    return redirect(url_for('tournaments.detail',tid=tid))

@bp.post('/<int:tid>/unregister/<int:team_id>')
@login_required
def unregister(tid,team_id):
    t=Tournament.query.get_or_404(tid); team=Team.query.get_or_404(team_id)
    if not (current_user.is_admin or team.owner_id==current_user.id): abort(403)
    if not t.is_open: flash('As inscrições estão fechadas. Fale com a organização para cancelar.','danger'); return redirect(url_for('tournaments.detail',tid=tid))
    reg=TournamentRegistration.query.filter_by(tournament_id=tid,team_id=team_id).first_or_404()
    db.session.delete(reg); db.session.commit(); flash(f'Inscrição do {team.name} cancelada.','info')
    return redirect(url_for('tournaments.detail',tid=tid))
