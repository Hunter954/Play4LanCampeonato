from flask import Blueprint, render_template, redirect, url_for, abort, flash
from flask_login import login_required, current_user
from web.extensions import db
from web.models import Tournament, TournamentRegistration, Team
bp=Blueprint('tournaments',__name__,url_prefix='/tournaments')
@bp.get('/<int:tid>')
def detail(tid):
    t=Tournament.query.get_or_404(tid)
    regs=TournamentRegistration.query.filter_by(tournament_id=tid).order_by(TournamentRegistration.id).all()
    my_teams=[]
    if current_user.is_authenticated:
        my_teams=Team.query.filter((Team.owner_id==current_user.id)).all()
    return render_template('tournaments/detail.html',t=t,regs=regs,my_teams=my_teams)
@bp.post('/<int:tid>/register/<int:team_id>')
@login_required
def register(tid,team_id):
    t=Tournament.query.get_or_404(tid); team=Team.query.get_or_404(team_id)
    if not (current_user.is_admin or team.owner_id==current_user.id): abort(403)
    if len(team.members)!=5: flash('O time precisa ter exatamente 5 jogadores no MVP.','danger'); return redirect(url_for('tournaments.detail',tid=tid))
    if not TournamentRegistration.query.filter_by(tournament_id=tid,team_id=team_id).first(): db.session.add(TournamentRegistration(tournament_id=tid,team_id=team_id)); db.session.commit()
    return redirect(url_for('tournaments.detail',tid=tid))
