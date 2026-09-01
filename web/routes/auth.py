import os, re, requests
from urllib.parse import urlencode
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from flask_login import login_user, logout_user, current_user
from werkzeug.security import check_password_hash
from web.extensions import db
from web.models import User
bp=Blueprint('auth',__name__,url_prefix='/auth')

@bp.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=User.query.filter_by(email=request.form.get('email')).first()
        if u and u.password_hash and check_password_hash(u.password_hash,request.form.get('password','')):
            login_user(u); return redirect(url_for('main.home'))
        flash('Login inválido.','danger')
    return render_template('login.html')

@bp.get('/logout')
def logout(): logout_user(); return redirect(url_for('main.home'))

@bp.get('/steam')
def steam_login():
    return_to=url_for('auth.steam_callback',_external=True)
    params={'openid.ns':'http://specs.openid.net/auth/2.0','openid.mode':'checkid_setup','openid.return_to':return_to,'openid.realm':os.getenv('STEAM_REALM',request.host_url.rstrip('/')),'openid.identity':'http://specs.openid.net/auth/2.0/identifier_select','openid.claimed_id':'http://specs.openid.net/auth/2.0/identifier_select'}
    session['post_steam_next']=request.args.get('next')
    return redirect('https://steamcommunity.com/openid/login?'+urlencode(params))

@bp.get('/steam/callback')
def steam_callback():
    args=request.args.to_dict(); verify=args.copy(); verify['openid.mode']='check_authentication'
    try: ok='is_valid:true' in requests.post('https://steamcommunity.com/openid/login',data=verify,timeout=10).text
    except requests.RequestException: ok=False
    if not ok: flash('Não foi possível validar o login Steam.','danger'); return redirect(url_for('auth.login'))
    claimed=args.get('openid.claimed_id',''); m=re.search(r'/openid/id/(\d+)$',claimed)
    if not m: flash('SteamID inválido.','danger'); return redirect(url_for('auth.login'))
    sid=m.group(1); u=User.query.filter_by(steam_id64=sid).first()
    if not u: u=User(steam_id64=sid); db.session.add(u)
    key=os.getenv('STEAM_API_KEY')
    if key:
        try:
            data=requests.get('https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/',params={'key':key,'steamids':sid},timeout=10).json(); p=data.get('response',{}).get('players',[{}])[0]
            u.steam_name=p.get('personaname'); u.steam_avatar=p.get('avatarfull'); u.steam_profile_url=p.get('profileurl'); u.nickname=u.nickname or p.get('personaname')
        except Exception: pass
    db.session.commit(); login_user(u)
    nxt=session.pop('post_steam_next',None); return redirect(nxt or url_for('auth.profile'))

@bp.route('/profile',methods=['GET','POST'])
def profile():
    if not current_user.is_authenticated: return redirect(url_for('auth.login'))
    if request.method=='POST':
        current_user.real_name=request.form.get('real_name'); current_user.nickname=request.form.get('nickname'); current_user.avatar_url=request.form.get('avatar_url') or current_user.steam_avatar
        db.session.commit(); flash('Perfil atualizado.','success')
    return render_template('profile.html')
