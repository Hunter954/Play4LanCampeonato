from web.models import Team, TeamMember, User


def enrich_players(players):
    """Cruza SteamID64 do servidor com perfis da plataforma sem exigir cadastro."""
    rows = [dict(p or {}) for p in (players or [])]
    steam_ids = [str(p.get('steam_id64') or p.get('steam') or '').strip() for p in rows]
    steam_ids = [sid for sid in steam_ids if sid and sid.isdigit()]
    if not steam_ids:
        for p in rows:
            p['registered'] = False
        return rows

    users = User.query.filter(User.steam_id64.in_(steam_ids)).all()
    by_steam = {str(u.steam_id64): u for u in users if u.steam_id64}
    user_ids = [u.id for u in users]
    memberships = []
    if user_ids:
        memberships = (
            TeamMember.query
            .join(Team, Team.id == TeamMember.team_id)
            .filter(TeamMember.user_id.in_(user_ids))
            .all()
        )
    teams_by_user = {}
    for membership in memberships:
        teams_by_user.setdefault(membership.user_id, []).append({
            'id': membership.team.id,
            'name': membership.team.name,
            'tag': membership.team.tag,
            'role': membership.role,
            'logo_url': membership.team.logo_url,
        })

    for p in rows:
        sid = str(p.get('steam_id64') or p.get('steam') or '').strip()
        user = by_steam.get(sid)
        if not user:
            p['registered'] = False
            continue
        p.update({
            'registered': True,
            'platform_user_id': user.id,
            'platform_nickname': user.nickname or user.steam_name or p.get('name'),
            'real_name': user.real_name,
            'avatar_url': user.avatar_url or user.steam_avatar,
            'steam_profile_url': user.steam_profile_url,
            'platform_teams': teams_by_user.get(user.id, []),
        })
    return rows


def enrich_telemetry(telemetry):
    data = dict(telemetry or {})
    data['players'] = enrich_players(data.get('players', []))
    data['player_count'] = len(data['players'])
    return data
