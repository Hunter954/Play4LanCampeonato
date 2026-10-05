import re
from flask import Blueprint, render_template, redirect, url_for, abort, flash, request, jsonify
from flask_login import login_required, current_user
from web.extensions import db
from web.models import Tournament, TournamentRegistration, Team, Match, ROSTER_SIZE, ACTIVE_REG_STATUSES
from web.routes.auth import onboarded_required
from web import registrations, payments, stats, bracket
bp=Blueprint('tournaments',__name__,url_prefix='/tournaments')

EMAIL_RE=re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

def _tournament_context(t):
    regs=TournamentRegistration.query.filter(TournamentRegistration.tournament_id==t.id,TournamentRegistration.status.in_(ACTIVE_REG_STATUSES)).order_by(TournamentRegistration.paid_at.is_(None),TournamentRegistration.paid_at,TournamentRegistration.id).all()
    return {'t':t,'confirmed':[r for r in regs if r.status=='APPROVED'],'regs':regs,'slots_left':registrations.slots_left(t),'roster_size':ROSTER_SIZE,
            'live':Match.query.filter_by(tournament_id=t.id,status='LIVE').all()}

@bp.get('/')
def index():
    return render_template('tournaments/index.html',tournaments=Tournament.query.order_by(Tournament.id.desc()).all())

@bp.get('/<int:tid>')
def detail(tid):
    t=Tournament.query.get_or_404(tid); ctx=_tournament_context(t)
    my_teams=[]
    if current_user.is_authenticated:
        for team in Team.query.filter(Team.owner_id==current_user.id).order_by(Team.name).all():
            reg=TournamentRegistration.query.filter_by(tournament_id=t.id,team_id=team.id).filter(TournamentRegistration.status.in_(ACTIVE_REG_STATUSES)).first()
            my_teams.append({'team':team,'reg':reg,'problems':[] if reg else registrations.problems(t,team)})
    my_reg=None
    if current_user.is_authenticated and not my_teams:
        ids=[m.team_id for m in current_user.memberships]
        my_reg=TournamentRegistration.query.filter(TournamentRegistration.tournament_id==t.id,TournamentRegistration.team_id.in_(ids or [0]),TournamentRegistration.status.in_(ACTIVE_REG_STATUSES)).first()
    return render_template('tournaments/detail.html',my_teams=my_teams,my_reg=my_reg,tab='overview',**ctx)

@bp.get('/<int:tid>/chave')
def bracket_view(tid):
    t=Tournament.query.get_or_404(tid)
    upper,lower,final,by_id=bracket.columns(t)
    return render_template('tournaments/bracket.html',upper=upper,lower=lower,final=final,by_id=by_id,describe=bracket.describe_source,code=bracket.match_code,tab='bracket',**_tournament_context(t))

@bp.get('/<int:tid>/partidas')
def matches(tid):
    t=Tournament.query.get_or_404(tid)
    ms=Match.query.filter_by(tournament_id=t.id).filter(Match.bracket.isnot(None)).all()
    order={'LIVE':0,'LOADED':1,'CONFIGURED':2,'VETO':3,'READY':4,'WAITING':5,'FINISHED':6}
    visible=[m for m in ms if not (m.walkover and (not m.team1_id or not m.team2_id))]
    visible.sort(key=lambda m:(order.get(m.status,9),{'UPPER':0,'LOWER':1,'FINAL':2}.get(m.bracket,3),m.round or 0,m.position or 0))
    _,_,_,by_id=bracket.columns(t)
    return render_template('tournaments/matches.html',matches=visible,by_id=by_id,describe=bracket.describe_source,code=bracket.match_code,tab='matches',**_tournament_context(t))

@bp.get('/<int:tid>/estatisticas')
def leaderboard(tid):
    t=Tournament.query.get_or_404(tid)
    return render_template('tournaments/stats.html',players=stats.leaderboard(t),tab='stats',**_tournament_context(t))

@bp.post('/<int:tid>/register/<int:team_id>')
@onboarded_required
def register(tid,team_id):
    t=Tournament.query.get_or_404(tid); team=Team.query.get_or_404(team_id)
    if not (current_user.is_admin or team.owner_id==current_user.id): abort(403)
    existing=TournamentRegistration.query.filter_by(tournament_id=tid,team_id=team_id).filter(TournamentRegistration.status.in_(ACTIVE_REG_STATUSES)).first()
    if existing: return redirect(url_for('tournaments.registration',tid=tid,team_id=team_id))
    problems=registrations.problems(t,team)
    if problems:
        for p in problems: flash(p,'danger')
        return redirect(url_for('tournaments.detail',tid=tid))
    reg=registrations.get_or_create(t,team); db.session.commit()
    if reg.status=='APPROVED':
        flash(f'{team.name} está confirmado no {t.name}!','success'); return redirect(url_for('tournaments.detail',tid=tid))
    return redirect(url_for('tournaments.registration',tid=tid,team_id=team_id))

def _my_registration(tid,team_id):
    t=Tournament.query.get_or_404(tid); team=Team.query.get_or_404(team_id)
    if not (current_user.is_admin or team.has_member(current_user)): abort(403)
    reg=TournamentRegistration.query.filter_by(tournament_id=tid,team_id=team_id).first_or_404()
    return t,team,reg

@bp.get('/<int:tid>/inscricao/<int:team_id>')
@login_required
def registration(tid,team_id):
    t,team,reg=_my_registration(tid,team_id)
    p=reg.latest_payment
    if p and reg.status=='AWAITING_PAYMENT': registrations.sync(p); db.session.commit()
    return render_template('tournaments/registration.html',t=t,team=team,reg=reg,payment=p,is_captain=team.owner_id==current_user.id or current_user.is_admin,
                           mp_enabled=payments.enabled(),slots_left=registrations.slots_left(t,reg.id),roster_size=ROSTER_SIZE)

@bp.post('/<int:tid>/inscricao/<int:team_id>/pix')
@onboarded_required
def create_pix(tid,team_id):
    t,team,reg=_my_registration(tid,team_id)
    if team.owner_id!=current_user.id and not current_user.is_admin: abort(403)
    if reg.status!='AWAITING_PAYMENT': return redirect(url_for('tournaments.registration',tid=tid,team_id=team_id))
    email=(request.form.get('email') or '').strip().lower()
    if not EMAIL_RE.match(email):
        flash('Informe um e-mail válido para receber o comprovante.','danger'); return redirect(url_for('tournaments.registration',tid=tid,team_id=team_id))
    if registrations.slots_left(t,reg.id)<=0:
        flash('As vagas acabaram enquanto você se inscrevia. Fale com a organização.','danger'); return redirect(url_for('tournaments.registration',tid=tid,team_id=team_id))
    try:
        registrations.create_pix(reg,current_user,email,url_for('api.mercadopago_webhook',_external=True)); db.session.commit()
    except payments.PaymentError as e:
        db.session.rollback(); flash(str(e),'danger')
    return redirect(url_for('tournaments.registration',tid=tid,team_id=team_id))

@bp.get('/<int:tid>/inscricao/<int:team_id>/status')
@login_required
def registration_status(tid,team_id):
    t,team,reg=_my_registration(tid,team_id)
    p=reg.latest_payment
    if p and reg.status=='AWAITING_PAYMENT': registrations.sync(p); db.session.commit()
    return jsonify(status=reg.status,payment=p.status if p else None,open=bool(p and p.is_open))

@bp.post('/<int:tid>/unregister/<int:team_id>')
@login_required
def unregister(tid,team_id):
    t=Tournament.query.get_or_404(tid); team=Team.query.get_or_404(team_id)
    if not (current_user.is_admin or team.owner_id==current_user.id): abort(403)
    reg=TournamentRegistration.query.filter_by(tournament_id=tid,team_id=team_id).first_or_404()
    if reg.status!='AWAITING_PAYMENT' and not current_user.is_admin:
        flash('Inscrição paga só pode ser cancelada pela organização.','danger'); return redirect(url_for('tournaments.detail',tid=tid))
    reg.status='CANCELLED'
    for p in [reg.latest_payment] if reg.latest_payment else []:
        if p.is_open: p.status='cancelled'
    db.session.commit(); flash(f'Inscrição do {team.name} cancelada.','info')
    return redirect(url_for('tournaments.detail',tid=tid))
