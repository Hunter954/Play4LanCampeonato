from flask import Blueprint, render_template, jsonify, request, abort
from flask_login import current_user, login_required
from web.extensions import db, socketio
from web.models import Match, MatchMap
from web.maps import MAP_COLORS
from web import veto, stats, bracket
bp=Blueprint('matches',__name__,url_prefix='/partidas')

def _pool(m): return m.tournament.maps if m.tournament else []

def my_side(m):
    """Slot (1/2) do time em que o usuário é capitão nesta partida; admin pode agir pelos dois."""
    if not current_user.is_authenticated: return None
    for slot,team in ((1,m.team1),(2,m.team2)):
        if team and team.owner_id==current_user.id: return slot
    return None

def state_json(m):
    pool=_pool(m); vs=veto.state(m,pool)
    acted={a.map_name:{'action':a.action,'team':a.team.tag if a.team else None,'slot':m.slot_of(a.team_id)} for a in vs['actions']}
    maps=[{'number':mm.map_number,'name':mm.map_name,'status':mm.status,'team1':mm.team1_score,'team2':mm.team2_score,
           'picked_by':mm.picked_by.tag if mm.picked_by else 'Decisivo','winner_slot':m.slot_of(mm.winner_id)} for mm in m.maps_played]
    nxt=vs['next']
    return {'id':m.id,'status':m.status,'status_label':_label(m.status),'team1_score':m.team1_score or 0,'team2_score':m.team2_score or 0,
            'winner_slot':m.slot_of(m.winner_id),'round':m.round_number,'current_map':m.current_map,
            'veto':{'pool':[{'name':p,'color':MAP_COLORS.get(p,'#556'),**acted.get(p,{})} for p in pool],
                    'next':{'slot':nxt['slot'],'action':nxt['action'],'team':(m.team1 if nxt['slot']==1 else m.team2).tag} if nxt else None,
                    'my_slot':my_side(m),'is_admin':bool(current_user.is_authenticated and current_user.is_admin)},
            'maps':maps}

def _label(s):
    from flask import current_app
    return current_app.jinja_env.filters['label'](s)

@bp.get('/<int:mid>')
def detail(mid):
    m=db.get_or_404(Match,mid)
    upper,lower,final,by_id=bracket.columns(m.tournament) if m.tournament else ([],[],None,{})
    return render_template('matches/detail.html',m=m,board=stats.scoreboard(m),maps=m.maps_played,code=bracket.match_code(m) if m.bracket else '',
                           describe=bracket.describe_source,by_id=by_id,state=state_json(m),demos=[])

@bp.get('/<int:mid>/estado')
def state(mid):
    m=db.get_or_404(Match,mid)
    return jsonify(state_json(m))

@bp.get('/<int:mid>/placar')
def scoreboard_partial(mid):
    m=db.get_or_404(Match,mid)
    return render_template('matches/_scoreboard.html',m=m,board=stats.scoreboard(m),maps=m.maps_played)

@bp.post('/<int:mid>/veto')
@login_required
def veto_action(mid):
    m=db.get_or_404(Match,mid)
    data=request.get_json(silent=True) or request.form
    st=veto.state(m,_pool(m))
    if not st['next']: return jsonify(ok=False,error='O veto não está aberto.'),409
    slot=my_side(m)
    if current_user.is_admin and slot is None: slot=st['next']['slot']  # admin age pelo time da vez
    if slot is None: abort(403)
    team_id=m.team1_id if slot==1 else m.team2_id
    try:
        veto.apply(m,_pool(m),team_id,(data.get('map') or '').strip(),current_user.id)
    except ValueError as e:
        db.session.rollback(); return jsonify(ok=False,error=str(e)),409
    db.session.commit(); socketio.emit('match_update',{'match_id':m.id})
    return jsonify(ok=True,state=state_json(m))
