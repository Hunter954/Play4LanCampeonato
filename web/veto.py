"""Veto de mapas feito pelos capitães no site.

MD1: bans alternados (time 1 começa) até sobrar um mapa.
MD3: ban, ban, pick, pick, e bans alternados até sobrar o decisivo.
MD5: ban, ban, pick, pick, pick, pick, decisivo.
O lado de cada mapa é decidido no round faca (MatchZy).
"""
from web.extensions import db
from web.models import MatchMap, VetoAction


def plan(best_of, pool_size):
    """Lista de (slot do time, ação) até restar 1 mapa; o último mapa vira decisivo automaticamente."""
    steps = []
    if best_of <= 1:
        steps = [((i % 2) + 1, 'ban') for i in range(pool_size - 1)]
    else:
        picks = best_of - 1
        opening_bans = 2 if pool_size - picks - 1 >= 2 else max(0, pool_size - picks - 1)
        steps = [((i % 2) + 1, 'ban') for i in range(opening_bans)]
        steps += [((i % 2) + 1, 'pick') for i in range(picks)]
        remaining = pool_size - opening_bans - picks
        steps += [((i % 2) + 1, 'ban') for i in range(remaining - 1)]
    return steps


def state(match, pool):
    actions = VetoAction.query.filter_by(match_id=match.id).order_by(VetoAction.step).all()
    steps = plan(match.best_of or 1, len(pool))
    used = {a.map_name for a in actions}
    remaining = [m for m in pool if m not in used]
    nxt = None
    if match.status == 'VETO' and len(actions) < len(steps):
        slot, action = steps[len(actions)]
        nxt = {'step': len(actions), 'slot': slot, 'action': action, 'team_id': match.team1_id if slot == 1 else match.team2_id}
    return {'actions': actions, 'steps': steps, 'remaining': remaining, 'next': nxt, 'done': len(actions) >= len(steps)}


def apply(match, pool, team_id, map_name, user_id=None):
    st = state(match, pool)
    nxt = st['next']
    if not nxt: raise ValueError('O veto não está aberto.')
    if team_id != nxt['team_id']: raise ValueError('Não é a vez do seu time.')
    if map_name not in st['remaining']: raise ValueError('Esse mapa não está mais disponível.')
    db.session.add(VetoAction(match_id=match.id, step=nxt['step'], team_id=team_id, action=nxt['action'], map_name=map_name, user_id=user_id))
    db.session.flush()
    if len(st['actions']) + 1 >= len(st['steps']): finalize(match, pool)


def finalize(match, pool):
    actions = VetoAction.query.filter_by(match_id=match.id).order_by(VetoAction.step).all()
    used = {a.map_name for a in actions}
    picks = [(a.map_name, a.team_id) for a in actions if a.action == 'pick']
    decider = [m for m in pool if m not in used]
    maps = picks + [(decider[0], None)] if decider else picks
    set_maps(match, maps[:match.best_of or 1])


def set_maps(match, maps):
    """Define os mapas da série: lista de (nome, team_id que escolheu ou None)."""
    MatchMap.query.filter_by(match_id=match.id).delete()
    for i, (name, picked_by) in enumerate(maps, start=1):
        db.session.add(MatchMap(match_id=match.id, map_number=i, map_name=name, picked_by_id=picked_by))
    match.current_map = maps[0][0] if maps else None
    match.status = 'CONFIGURED'
    db.session.flush()


def reset(match):
    VetoAction.query.filter_by(match_id=match.id).delete()
    MatchMap.query.filter_by(match_id=match.id).delete()
    match.current_map = None
    match.status = 'READY'
    db.session.flush()
