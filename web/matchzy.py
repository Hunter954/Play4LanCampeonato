"""Integração com o MatchZy (base do plugin PLAY4LANCompetitive).

Fluxo:
1. Admin envia a partida ao servidor -> RCON `matchzy_loadmatch_url <config>` e, em seguida, `matchzy_remote_log_url <eventos>`.
   (O MatchZy recria a configuração ao carregar a partida, então a URL de eventos precisa vir DEPOIS.)
2. O servidor baixa a configuração (times, SteamIDs, mapas do veto, lados no round faca).
3. Durante o jogo o MatchZy envia eventos: going_live, round_end (com stats de todos), map_result, series_end.
4. series_end define o vencedor e avança a chave.
Fallback: se os eventos não chegarem, a telemetria do Agent (K/D/A/dano) alimenta o placar e as estatísticas básicas.
"""
from datetime import datetime
from web.extensions import db
from web.models import Match, MatchMap, PlayerMapStat, User, Team
from web.maps import server_name, display_name
from web import bracket

MATCHZY_STATS = {'kills': 'kills', 'deaths': 'deaths', 'assists': 'assists', 'damage': 'damage', 'headshot_kills': 'headshot_kills',
                 'rounds_played': 'rounds_played', 'kast': 'kast', 'mvp': 'mvp', 'score': 'score', 'utility_damage': 'utility_damage',
                 'enemies_flashed': 'enemies_flashed', 'flash_assists': 'flash_assists', 'trade_kills': 'trade_kills',
                 'bomb_plants': 'bomb_plants', 'bomb_defuses': 'bomb_defuses', 'k1': '1k', 'k2': '2k', 'k3': '3k', 'k4': '4k', 'k5': '5k'}


def _players(team):
    return {m.user.steam_id64: m.user.display_name for m in team.roster if m.user.steam_id64}


def config(match):
    maps = match.maps_played
    t1, t2 = match.team1, match.team2
    return {
        'matchid': match.id,
        'team1': {'id': str(t1.id), 'name': t1.name, 'tag': t1.tag, 'players': _players(t1)},
        'team2': {'id': str(t2.id), 'name': t2.name, 'tag': t2.tag, 'players': _players(t2)},
        'num_maps': match.best_of or 1,
        'maplist': [server_name(m.map_name) for m in maps],
        'map_sides': ['knife'] * len(maps),
        'skip_veto': True,
        'clinch_series': True,
        'players_per_team': 5,
        'cvars': {'hostname': f'PLAY4LAN | {t1.tag} vs {t2.tag}'},
    }


def load_commands(match, base_url):
    base = base_url.rstrip('/')
    cfg = f'{base}/api/v1/matches/{match.id}/config?token={match.config_token}'
    events = f'{base}/api/v1/matchzy/events?token={match.config_token}'
    return [f'matchzy_loadmatch_url "{cfg}"', f'matchzy_remote_log_url "{events}"']


def _team_from_event(match, team_json):
    tid = str((team_json or {}).get('id') or '')
    if tid.isdigit() and int(tid) in (match.team1_id, match.team2_id): return int(tid)
    return None


def _store_team_stats(match, map_number, team_json, team_id):
    for p in (team_json or {}).get('players') or []:
        sid = str(p.get('steamid') or '')
        if not sid.isdigit() or sid == '0': continue
        st = p.get('stats') or {}
        row = PlayerMapStat.query.filter_by(match_id=match.id, map_number=map_number, steam_id64=sid).first()
        if not row:
            row = PlayerMapStat(match_id=match.id, map_number=map_number, steam_id64=sid); db.session.add(row)
        user = User.query.filter_by(steam_id64=sid).first()
        row.user_id = user.id if user else None; row.team_id = team_id; row.name = p.get('name') or row.name; row.source = 'matchzy'
        for field, key in MATCHZY_STATS.items(): setattr(row, field, int(st.get(key) or 0))
        row.first_kills = int(st.get('first_kills_t') or 0) + int(st.get('first_kills_ct') or 0)
        row.first_deaths = int(st.get('first_deaths_t') or 0) + int(st.get('first_deaths_ct') or 0)
        row.clutches_won = sum(int(st.get(f'1v{i}') or 0) for i in range(1, 6))


def _map_row(match, map_number):
    mm = MatchMap.query.filter_by(match_id=match.id, map_number=map_number).first()
    if not mm:
        mm = MatchMap(match_id=match.id, map_number=map_number, map_name=match.current_map or '?'); db.session.add(mm)
    return mm


def _apply_scores(match, mm, t1, t2):
    mm.team1_score = int((t1 or {}).get('score') or 0); mm.team2_score = int((t2 or {}).get('score') or 0)
    if (match.best_of or 1) == 1:
        match.team1_score, match.team2_score = mm.team1_score, mm.team2_score


def handle_event(match, ev):
    """Processa um evento do MatchZy. Retorna True se mudou algo relevante para a tela."""
    name = ev.get('event')
    map_number = int(ev.get('map_number') or 0) + 1  # MatchZy numera mapas a partir de 0
    if name == 'going_live':
        mm = _map_row(match, map_number); mm.status = 'LIVE'
        match.status = 'LIVE'; match.started_at = match.started_at or datetime.utcnow(); match.current_map = mm.map_name
        return True
    if name in ('round_end', 'map_result'):
        mm = _map_row(match, map_number)
        t1, t2 = ev.get('team1') or {}, ev.get('team2') or {}
        id1, id2 = _team_from_event(match, t1) or match.team1_id, _team_from_event(match, t2) or match.team2_id
        if id1 == match.team2_id:  # garante team1 do evento = team1 da partida
            t1, t2, id1, id2 = t2, t1, id2, id1
        _apply_scores(match, mm, t1, t2)
        _store_team_stats(match, map_number, t1, id1); _store_team_stats(match, map_number, t2, id2)
        match.round_number = int(ev.get('round_number') or match.round_number or 0)
        if match.status not in ('LIVE', 'FINISHED'): match.status = 'LIVE'
        if name == 'map_result':
            mm.status = 'FINISHED'
            mm.winner_id = match.team1_id if mm.team1_score > mm.team2_score else match.team2_id if mm.team2_score > mm.team1_score else None
            if (match.best_of or 1) > 1:
                done = MatchMap.query.filter_by(match_id=match.id, status='FINISHED').all()
                match.team1_score = sum(1 for m in done if m.winner_id == match.team1_id)
                match.team2_score = sum(1 for m in done if m.winner_id == match.team2_id)
        return True
    if name == 'series_end':
        if match.status == 'FINISHED': return False
        winner = (ev.get('winner') or {}).get('team')
        wid = match.team1_id if winner == 'team1' else match.team2_id if winner == 'team2' else None
        if (match.best_of or 1) > 1:
            match.team1_score = int(ev.get('team1_series_score') or match.team1_score or 0)
            match.team2_score = int(ev.get('team2_series_score') or match.team2_score or 0)
        if not wid:
            wid = match.team1_id if match.team1_score > match.team2_score else match.team2_id if match.team2_score > match.team1_score else None
        if wid:
            bracket.finish(match, wid, walkover=False)
            release_server(match)
        return True
    return False


def release_server(match):
    from web.models import Server
    for s in Server.query.filter_by(current_match_id=match.id).all(): s.current_match_id = None


def telemetry_fallback(match, telemetry):
    """Placar e K/D/A/dano a partir da telemetria do Agent, quando o MatchZy não envia eventos."""
    if match.status not in ('LOADED', 'LIVE'): return False
    players = telemetry.get('players') or []
    if not any('kills' in p for p in players): return False
    mm = MatchMap.query.filter_by(match_id=match.id).filter(MatchMap.status != 'FINISHED').order_by(MatchMap.map_number).first()
    if not mm: return False
    if PlayerMapStat.query.filter_by(match_id=match.id, map_number=mm.map_number, source='matchzy').first(): return False
    t1s, t2s = telemetry.get('team1_score'), telemetry.get('team2_score')
    if t1s is not None and t2s is not None:
        mm.team1_score, mm.team2_score = int(t1s or 0), int(t2s or 0)
        if (match.best_of or 1) == 1: match.team1_score, match.team2_score = mm.team1_score, mm.team2_score
    rounds = (mm.team1_score or 0) + (mm.team2_score or 0)
    roster = {}
    for team in (match.team1, match.team2):
        for m in team.members:
            if m.user.steam_id64: roster[m.user.steam_id64] = (team.id, m.user)
    for p in players:
        sid = str(p.get('steam_id64') or '')
        if sid not in roster: continue
        team_id, user = roster[sid]
        row = PlayerMapStat.query.filter_by(match_id=match.id, map_number=mm.map_number, steam_id64=sid).first()
        if not row:
            row = PlayerMapStat(match_id=match.id, map_number=mm.map_number, steam_id64=sid); db.session.add(row)
        row.user_id = user.id; row.team_id = team_id; row.name = p.get('name'); row.source = 'telemetry'
        row.kills = int(p.get('kills') or 0); row.deaths = int(p.get('deaths') or 0); row.assists = int(p.get('assists') or 0)
        row.damage = int(p.get('damage') or 0); row.rounds_played = rounds
    if match.status == 'LOADED' and rounds > 0: match.status = 'LIVE'; match.started_at = match.started_at or datetime.utcnow()
    return True
