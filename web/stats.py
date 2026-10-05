"""Estatísticas de jogadores (por mapa, por partida, por campeonato e carreira)."""
from collections import OrderedDict
from web.extensions import db
from web.models import PlayerMapStat, Match, MatchMap, User, STAT_FIELDS


def rating(kills, deaths, rounds, k1=0, k2=0, k3=0, k4=0, k5=0):
    """Rating 1.0 (fórmula pública do HLTV)."""
    if not rounds: return None
    multi = k1 + 4 * k2 + 9 * k3 + 16 * k4 + 25 * k5
    if not multi and kills: multi = kills  # telemetria sem multikills: trata cada abate como round de 1 kill
    return round((kills / rounds / 0.679 + 0.7 * (rounds - deaths) / rounds / 0.317 + multi / rounds / 1.277) / 2.7, 2)


def summarize(rows):
    """Soma linhas de PlayerMapStat (ou dicts) e calcula as métricas."""
    total = {f: 0 for f in STAT_FIELDS}
    maps = 0; has_hs = False
    for r in rows:
        maps += 1
        for f in STAT_FIELDS: total[f] += int(getattr(r, f, 0) or 0)
        if getattr(r, 'source', 'matchzy') == 'matchzy': has_hs = True
    k, d, rounds = total['kills'], total['deaths'], total['rounds_played']
    total.update({
        'maps': maps,
        'kd': round(k / d, 2) if d else float(k),
        'diff': k - d,
        'adr': round(total['damage'] / rounds, 1) if rounds else None,
        'hs_pct': round(100 * total['headshot_kills'] / k) if k and has_hs else None,
        'kast_pct': round(100 * total['kast'] / rounds) if rounds and has_hs else None,
        'multikills': total['k3'] + total['k4'] + total['k5'],
        'rating': rating(k, d, rounds, total['k1'], total['k2'], total['k3'], total['k4'], total['k5']),
    })
    return total


def scoreboard(match):
    """Por mapa: {map_number: {team_id: [linhas ordenadas]}} com métricas calculadas."""
    rows = PlayerMapStat.query.filter_by(match_id=match.id).all()
    out = OrderedDict()
    for mm in sorted({r.map_number for r in rows}):
        teams = {}
        for r in [r for r in rows if r.map_number == mm]:
            s = summarize([r]); s.update({'name': r.user.display_name if r.user else r.name, 'user': r.user, 'steam_id64': r.steam_id64, 'source': r.source})
            teams.setdefault(r.team_id, []).append(s)
        for tid in teams: teams[tid].sort(key=lambda s: (s['rating'] or 0, s['kills']), reverse=True)
        out[mm] = teams
    return out


def _grouped(rows):
    by = OrderedDict()
    for r in rows: by.setdefault(r.steam_id64, []).append(r)
    out = []
    for sid, rs in by.items():
        s = summarize(rs)
        u = next((r.user for r in rs if r.user), None)
        s.update({'steam_id64': sid, 'user': u, 'name': u.display_name if u else rs[-1].name, 'team': rs[-1].team})
        out.append(s)
    return out


def leaderboard(tournament, min_maps=1):
    rows = PlayerMapStat.query.join(Match, Match.id == PlayerMapStat.match_id).filter(Match.tournament_id == tournament.id).all()
    players = [p for p in _grouped(rows) if p['maps'] >= min_maps]
    players.sort(key=lambda s: (s['rating'] or 0, s['kd']), reverse=True)
    return players


def player_career(user):
    rows = PlayerMapStat.query.filter_by(steam_id64=user.steam_id64).order_by(PlayerMapStat.match_id.desc(), PlayerMapStat.map_number).all() if user.steam_id64 else []
    recent = []
    for r in rows[:15]:
        m = db.session.get(Match, r.match_id)
        mm = MatchMap.query.filter_by(match_id=r.match_id, map_number=r.map_number).first()
        s = summarize([r]); s.update({'match': m, 'map': mm.map_name if mm else (m.current_map if m else '?'), 'team_id': r.team_id,
                                      'won': bool(mm and mm.winner_id and mm.winner_id == r.team_id)})
        recent.append(s)
    return summarize(rows), recent
