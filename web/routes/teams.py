import re, secrets
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from web.extensions import db
from web.models import Team, TeamMember, Invite, TournamentRegistration, Match, Payment, ROSTER_SIZE, ACTIVE_REG_STATUSES
from web.routes.auth import onboarded_required
from web import media
bp=Blueprint('teams',__name__,url_prefix='/teams')

TAG_RE=re.compile(r'^[A-Za-z0-9]{2,5}$')

def owner(team): return current_user.is_authenticated and (current_user.is_admin or team.owner_id==current_user.id)

def _roster_locked(team):
    reg=team.locking_registration
    if reg: flash(f'O elenco está travado pela inscrição no {reg.tournament.name}. Fale com a organização para trocar jogadores.','danger')
    return bool(reg)

def _active_registrations(team):
    return TournamentRegistration.query.filter(TournamentRegistration.team_id==team.id, TournamentRegistration.status.in_(ACTIVE_REG_STATUSES)).count()

def _validate_team_form(f, team=None):
    name=(f.get('name') or '').strip()[:40]; tag=(f.get('tag') or '').strip().upper()
    errors=[]
    if len(name)<3: errors.append('O nome do time precisa ter pelo menos 3 caracteres.')
    if not TAG_RE.match(tag): errors.append('A tag precisa ter de 2 a 5 letras ou números, sem espaços.')
    q=Team.query.filter(Team.id!=team.id) if team else Team.query
    if name and q.filter(db.func.lower(Team.name)==name.lower()).first(): errors.append('Já existe um time com esse nome.')
    if tag and q.filter(db.func.upper(Team.tag)==tag).first(): errors.append('Essa tag já está em uso por outro time.')
    data={'name':name,'tag':tag,'description':(f.get('description') or '').strip()[:280] or None}
    upload=request.files.get('logo')
    if not errors and upload and upload.filename:
        try: data['logo_url']=media.save_image(upload,'logo',current_user.id)
        except ValueError as e: errors.append(str(e))
    elif f.get('remove_logo')=='1': data['logo_url']=None
    return data, errors

@bp.get('/')
def index():
    q=(request.args.get('q') or '').strip()
    query=Team.query
    if q: query=query.filter(db.or_(Team.name.ilike(f'%{q}%'), Team.tag.ilike(f'%{q}%')))
    return render_template('teams/index.html',teams=query.order_by(Team.created_at.desc()).all(),q=q)

@bp.route('/create',methods=['GET','POST'])
@onboarded_required
def create():
    if request.method=='POST':
        data,errors=_validate_team_form(request.form)
        if errors:
            db.session.rollback()
            for e in errors: flash(e,'danger')
            return render_template('teams/create.html',form=request.form,team=None),400
        t=Team(owner_id=current_user.id,**data); db.session.add(t); db.session.flush()
        db.session.add(TeamMember(team_id=t.id,user_id=current_user.id,role='OWNER'))
        db.session.add(Invite(token=secrets.token_urlsafe(24),team_id=t.id,created_by=current_user.id))
        db.session.commit(); flash(f'Time {t.name} criado! Envie o link de convite para seus jogadores.','success')
        return redirect(url_for('teams.detail',team_id=t.id))
    return render_template('teams/create.html',form=None,team=None)

@bp.route('/<int:team_id>/edit',methods=['GET','POST'])
@onboarded_required
def edit(team_id):
    t=Team.query.get_or_404(team_id)
    if not owner(t): abort(403)
    if request.method=='POST':
        data,errors=_validate_team_form(request.form,t)
        if errors:
            db.session.rollback()
            for e in errors: flash(e,'danger')
            return render_template('teams/create.html',form=request.form,team=t),400
        if 'logo_url' in data: media.delete_if_local(t.logo_url)
        for k,v in data.items(): setattr(t,k,v)
        db.session.commit(); flash('Time atualizado.','success'); return redirect(url_for('teams.detail',team_id=t.id))
    return render_template('teams/create.html',form=t.__dict__,team=t)

@bp.get('/<int:team_id>')
def detail(team_id):
    team=Team.query.get_or_404(team_id)
    can_manage=owner(team)
    invite=Invite.query.filter_by(team_id=team.id,active=True).order_by(Invite.id.desc()).first() if can_manage else None
    regs=TournamentRegistration.query.filter_by(team_id=team.id).order_by(TournamentRegistration.id.desc()).all()
    matches=Match.query.filter(db.or_(Match.team1_id==team.id,Match.team2_id==team.id)).order_by(Match.id.desc()).limit(10).all()
    return render_template('teams/detail.html',team=team,can_manage=can_manage,invite=invite,regs=regs,matches=matches,
                           is_member=team.has_member(current_user if current_user.is_authenticated else None),roster_size=ROSTER_SIZE)

@bp.post('/<int:team_id>/invite')
@login_required
def invite(team_id):
    t=Team.query.get_or_404(team_id)
    if not owner(t): abort(403)
    Invite.query.filter_by(team_id=t.id,active=True).update({'active':False})
    db.session.add(Invite(token=secrets.token_urlsafe(24),team_id=t.id,created_by=current_user.id)); db.session.commit()
    flash('Novo link de convite gerado. O link antigo deixou de funcionar.','success'); return redirect(url_for('teams.detail',team_id=t.id))

@bp.get('/invite/<token>')
def invite_landing(token):
    inv=Invite.query.filter_by(token=token,active=True).first()
    if not inv: return render_template('teams/invite.html',inv=None,team=None,roster_size=ROSTER_SIZE),404
    team=inv.team
    return render_template('teams/invite.html',inv=inv,team=team,roster_size=ROSTER_SIZE,
                           already=team.has_member(current_user if current_user.is_authenticated else None))

@bp.post('/invite/<token>/accept')
@onboarded_required
def accept_invite(token):
    inv=Invite.query.filter_by(token=token,active=True).first_or_404(); team=inv.team
    if team.has_member(current_user): return redirect(url_for('teams.detail',team_id=team.id))
    if team.is_full:
        flash(f'O time {team.name} já está completo ({ROSTER_SIZE}/{ROSTER_SIZE}).','danger'); return redirect(url_for('teams.invite_landing',token=token))
    db.session.add(TeamMember(team_id=team.id,user_id=current_user.id)); db.session.commit()
    flash(f'Bem-vindo ao {team.name}!','success'); return redirect(url_for('teams.detail',team_id=team.id))

@bp.post('/<int:team_id>/leave')
@login_required
def leave(team_id):
    t=Team.query.get_or_404(team_id)
    if t.owner_id==current_user.id:
        flash('O capitão não pode sair. Passe a capitania para outro jogador ou exclua o time.','danger'); return redirect(url_for('teams.detail',team_id=t.id))
    m=TeamMember.query.filter_by(team_id=t.id,user_id=current_user.id).first_or_404()
    if _roster_locked(t): return redirect(url_for('teams.detail',team_id=t.id))
    db.session.delete(m); db.session.commit(); flash(f'Você saiu do {t.name}.','info'); return redirect(url_for('main.account'))

@bp.post('/<int:team_id>/remove/<int:user_id>')
@login_required
def remove_member(team_id,user_id):
    t=Team.query.get_or_404(team_id)
    if not owner(t) or user_id==t.owner_id: abort(403)
    m=TeamMember.query.filter_by(team_id=team_id,user_id=user_id).first_or_404()
    if not current_user.is_admin and _roster_locked(t): return redirect(url_for('teams.detail',team_id=t.id))
    name=m.user.display_name; db.session.delete(m); db.session.commit()
    flash(f'{name} foi removido do time.','info'); return redirect(url_for('teams.detail',team_id=team_id))

@bp.post('/<int:team_id>/captain/<int:user_id>')
@login_required
def transfer_captain(team_id,user_id):
    t=Team.query.get_or_404(team_id)
    if not owner(t): abort(403)
    new=TeamMember.query.filter_by(team_id=t.id,user_id=user_id).first_or_404()
    old=TeamMember.query.filter_by(team_id=t.id,user_id=t.owner_id).first()
    if old: old.role='PLAYER'
    new.role='OWNER'; t.owner_id=user_id; db.session.commit()
    flash(f'{new.user.display_name} agora é o capitão do time.','success'); return redirect(url_for('teams.detail',team_id=t.id))

@bp.post('/<int:team_id>/delete')
@login_required
def delete(team_id):
    t=Team.query.get_or_404(team_id)
    if not owner(t): abort(403)
    if _active_registrations(t) or Match.query.filter(db.or_(Match.team1_id==t.id,Match.team2_id==t.id)).first():
        flash('Esse time tem inscrição ou partida em campeonato e não pode ser excluído. Fale com a organização.','danger')
        return redirect(url_for('teams.detail',team_id=t.id))
    reg_ids=[r.id for r in TournamentRegistration.query.filter_by(team_id=t.id).all()]
    if reg_ids: Payment.query.filter(Payment.registration_id.in_(reg_ids)).delete(synchronize_session=False)
    TournamentRegistration.query.filter_by(team_id=t.id).delete(); Invite.query.filter_by(team_id=t.id).delete()
    media.delete_if_local(t.logo_url)
    name=t.name; db.session.delete(t); db.session.commit()
    flash(f'O time {name} foi excluído.','info'); return redirect(url_for('main.account'))
