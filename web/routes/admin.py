from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, abort
from flask_login import current_user, login_required
from web.extensions import db
from web.models import Tournament, TournamentRegistration, Server, Match, Demo, ServerCommand
bp=Blueprint('admin',__name__,url_prefix='/admin')
def admin_only(fn):
    @wraps(fn)
    @login_required
    def inner(*a,**k):
        if not current_user.is_admin: abort(403)
        return fn(*a,**k)
    return inner
@bp.get('/')
@admin_only
def dashboard(): return render_template('admin/dashboard.html',servers=Server.query.order_by(Server.code).all(), regs=TournamentRegistration.query.order_by(TournamentRegistration.id.desc()).limit(20).all(), matches=Match.query.order_by(Match.id.desc()).limit(20).all())
@bp.route('/tournaments/create',methods=['GET','POST'])
@admin_only
def create_tournament():
    if request.method=='POST':
        t=Tournament(name=request.form['name'],description=request.form.get('description'),max_teams=int(request.form.get('max_teams',16))); db.session.add(t); db.session.commit(); return redirect(url_for('tournaments.detail',tid=t.id))
    return render_template('admin/create_tournament.html')
@bp.post('/registration/<int:rid>/<status>')
@admin_only
def registration_status(rid,status):
    if status not in {'APPROVED','REJECTED'}: abort(400)
    r=TournamentRegistration.query.get_or_404(rid); r.status=status; db.session.commit(); return redirect(url_for('admin.dashboard'))

@bp.post('/servers/<code>/<action>')
@admin_only
def server_action(code, action):
    if action not in {'START','STOP','RESTART'}: abort(400)
    s=Server.query.filter_by(code=code).first_or_404()
    if not s.host_id: abort(409)
    db.session.add(ServerCommand(host_id=s.host_id,server_code=s.code,command=action,payload={})); db.session.commit()
    return redirect(url_for('admin.dashboard'))
