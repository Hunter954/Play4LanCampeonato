import os, re, requests
from datetime import datetime
from functools import wraps
from urllib.parse import urlencode
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import check_password_hash
from web.extensions import db
from web.models import User
from web import media
bp=Blueprint('auth',__name__,url_prefix='/auth')

def safe_next(value):
    """Só aceita caminhos internos, evitando redirecionar para outro site."""
    value=(value or '').strip()
    return value if value.startswith('/') and not value.startswith('//') and '\\' not in value else None

def onboarded_required(fn):
    @wraps(fn)
    @login_required
    def inner(*a, **k):
        if not current_user.is_onboarded:
            flash('Complete seu cadastro antes de continuar.','info')
            return redirect(url_for('auth.profile', next=request.full_path.rstrip('?') if request.method=='GET' else None))
        return fn(*a, **k)
    return inner

def admin_steam_ids():
    """SteamID64 que viram admin automaticamente ao entrar (variável ADMIN_STEAM_IDS, separados por vírgula)."""
    return {s.strip() for s in (os.getenv('ADMIN_STEAM_IDS') or '').replace(';', ',').split(',') if s.strip().isdigit()}

def after_login_redirect(user, nxt=None):
    if user.is_admin and nxt and nxt.startswith('/admin'): return redirect(nxt)
    if not user.is_onboarded: return redirect(url_for('auth.profile', next=nxt) if nxt else url_for('auth.profile'))
    return redirect(nxt or url_for('main.account'))

@bp.get('/entrar')
def entrar():
    nxt=safe_next(request.args.get('next'))
    if current_user.is_authenticated: return redirect(nxt or url_for('main.account'))
    return render_template('entrar.html', next=nxt)

@bp.route('/login',methods=['GET','POST'])
def login():
    nxt=safe_next(request.args.get('next'))
    if request.method=='GET' and current_user.is_authenticated and current_user.is_admin:
        return redirect(nxt or url_for('admin.dashboard'))
    if request.method=='POST':
        u=User.query.filter_by(email=(request.form.get('email') or '').strip().lower()).first() or User.query.filter_by(email=request.form.get('email')).first()
        if u and u.password_hash and check_password_hash(u.password_hash,request.form.get('password','')):
            login_user(u); return redirect((nxt or url_for('admin.dashboard')) if u.is_admin else url_for('main.home'))
        flash('E-mail ou senha incorretos.','danger')
    return render_template('login.html', next=nxt)

@bp.get('/logout')
def logout(): logout_user(); flash('Você saiu da sua conta.','info'); return redirect(url_for('main.home'))

@bp.get('/steam')
def steam_login():
    return_to=url_for('auth.steam_callback',_external=True)
    # A Steam exige que return_to esteja dentro do realm; um STEAM_REALM de outro domínio quebraria o login.
    realm=(os.getenv('STEAM_REALM') or '').rstrip('/')
    if not realm or not return_to.startswith(realm+'/'): realm=request.host_url.rstrip('/')
    params={'openid.ns':'http://specs.openid.net/auth/2.0','openid.mode':'checkid_setup','openid.return_to':return_to,'openid.realm':realm,'openid.identity':'http://specs.openid.net/auth/2.0/identifier_select','openid.claimed_id':'http://specs.openid.net/auth/2.0/identifier_select'}
    session['post_steam_next']=safe_next(request.args.get('next'))
    return redirect('https://steamcommunity.com/openid/login?'+urlencode(params))

def refresh_steam_profile(u):
    key=os.getenv('STEAM_API_KEY')
    if not key: return
    try:
        data=requests.get('https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/',params={'key':key,'steamids':u.steam_id64},timeout=10).json(); p=(data.get('response',{}).get('players') or [{}])[0]
        u.steam_name=p.get('personaname') or u.steam_name; u.steam_avatar=p.get('avatarfull') or u.steam_avatar; u.steam_profile_url=p.get('profileurl') or u.steam_profile_url
    except Exception: pass

@bp.get('/steam/callback')
def steam_callback():
    args=request.args.to_dict(); verify=args.copy(); verify['openid.mode']='check_authentication'
    try: ok='is_valid:true' in requests.post('https://steamcommunity.com/openid/login',data=verify,timeout=10).text
    except requests.RequestException: ok=False
    if not ok: flash('Não foi possível validar o login Steam. Tente novamente.','danger'); return redirect(url_for('auth.entrar'))
    claimed=args.get('openid.claimed_id',''); m=re.search(r'^https://steamcommunity\.com/openid/id/(\d+)$',claimed)
    if not m: flash('SteamID inválido.','danger'); return redirect(url_for('auth.entrar'))
    sid=m.group(1); u=User.query.filter_by(steam_id64=sid).first()
    if not u: u=User(steam_id64=sid); db.session.add(u)
    if sid in admin_steam_ids(): u.is_admin=True
    refresh_steam_profile(u)
    u.steam_profile_url=u.steam_profile_url or f'https://steamcommunity.com/profiles/{sid}'
    u.last_login_at=datetime.utcnow()
    db.session.commit(); login_user(u, remember=True)
    return after_login_redirect(u, session.pop('post_steam_next',None))

@bp.route('/profile',methods=['GET','POST'])
@login_required
def profile():
    nxt=safe_next(request.args.get('next'))
    first_time=not current_user.is_onboarded
    if request.method=='POST':
        f=request.form
        nickname=(f.get('nickname') or '').strip()[:80]; real_name=(f.get('real_name') or '').strip()[:255]
        whatsapp=re.sub(r'[^\d+() -]','',f.get('whatsapp') or '').strip()[:32]
        errors=[]
        if len(nickname)<2: errors.append('Escolha um nick com pelo menos 2 caracteres.')
        if len(real_name.split())<2: errors.append('Informe seu nome e sobrenome.')
        taken=User.query.filter(db.func.lower(User.nickname)==nickname.lower(), User.id!=current_user.id).first() if nickname else None
        if taken: errors.append('Esse nick já está em uso na plataforma.')
        upload=request.files.get('avatar'); new_avatar=None
        if not errors and upload and upload.filename:
            try: new_avatar=media.save_image(upload,'avatar',current_user.id)
            except ValueError as e: errors.append(str(e))
        if errors:
            db.session.rollback()
            for e in errors: flash(e,'danger')
            return render_template('profile.html', first_time=first_time, next=nxt, form=f), 400
        current_user.nickname=nickname; current_user.real_name=real_name; current_user.whatsapp=whatsapp or None
        current_user.city=(f.get('city') or '').strip()[:80] or None; current_user.bio=(f.get('bio') or '').strip()[:280] or None
        if new_avatar or f.get('remove_avatar')=='1':
            media.delete_if_local(current_user.avatar_url); current_user.avatar_url=new_avatar
        if not current_user.onboarded_at: current_user.onboarded_at=datetime.utcnow()
        db.session.commit()
        flash('Cadastro concluído! Agora monte seu time.' if first_time else 'Perfil atualizado.','success')
        return redirect(nxt or url_for('main.account'))
    return render_template('profile.html', first_time=first_time, next=nxt, form=None)
