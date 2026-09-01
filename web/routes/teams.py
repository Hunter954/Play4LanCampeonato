import secrets
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from web.extensions import db
from web.models import Team, TeamMember, Invite
bp=Blueprint('teams',__name__,url_prefix='/teams')

def owner(team): return current_user.is_authenticated and (current_user.is_admin or team.owner_id==current_user.id)

@bp.get('/')
def index(): return render_template('teams/index.html',teams=Team.query.order_by(Team.name).all())

@bp.route('/create',methods=['GET','POST'])
@login_required
def create():
    if request.method=='POST':
        t=Team(name=request.form['name'].strip(),tag=request.form['tag'].strip().upper(),logo_url=request.form.get('logo_url'),owner_id=current_user.id); db.session.add(t); db.session.flush(); db.session.add(TeamMember(team_id=t.id,user_id=current_user.id,role='OWNER')); db.session.commit(); return redirect(url_for('teams.detail',team_id=t.id))
    return render_template('teams/create.html')

@bp.get('/<int:team_id>')
def detail(team_id):
    team=Team.query.get_or_404(team_id)
    invites=Invite.query.filter_by(team_id=team.id,active=True).order_by(Invite.id.desc()).limit(5).all() if current_user.is_authenticated and owner(team) else []
    return render_template('teams/detail.html',team=team,can_manage=current_user.is_authenticated and owner(team),invites=invites)

@bp.post('/<int:team_id>/invite')
@login_required
def invite(team_id):
    t=Team.query.get_or_404(team_id)
    if not owner(t): abort(403)
    inv=Invite(token=secrets.token_urlsafe(24),team_id=t.id,created_by=current_user.id); db.session.add(inv); db.session.commit(); flash('Link de convite criado.','success'); return redirect(url_for('teams.detail',team_id=t.id))

@bp.get('/invite/<token>')
def invite_landing(token):
    inv=Invite.query.filter_by(token=token,active=True).first_or_404()
    if not current_user.is_authenticated: return redirect(url_for('auth.steam_login',next=url_for('teams.accept_invite',token=token)))
    return redirect(url_for('teams.accept_invite',token=token))

@bp.get('/invite/<token>/accept')
@login_required
def accept_invite(token):
    inv=Invite.query.filter_by(token=token,active=True).first_or_404()
    if not TeamMember.query.filter_by(team_id=inv.team_id,user_id=current_user.id).first(): db.session.add(TeamMember(team_id=inv.team_id,user_id=current_user.id)); db.session.commit()
    return redirect(url_for('teams.detail',team_id=inv.team_id))

@bp.post('/<int:team_id>/remove/<int:user_id>')
@login_required
def remove_member(team_id,user_id):
    t=Team.query.get_or_404(team_id)
    if not owner(t) or user_id==t.owner_id: abort(403)
    m=TeamMember.query.filter_by(team_id=team_id,user_id=user_id).first_or_404(); db.session.delete(m); db.session.commit(); return redirect(url_for('teams.detail',team_id=team_id))
