"""Chaveamento em dupla eliminação (upper, lower e grande final).

Regras:
- Tamanho da chave = menor potência de 2 >= número de times (mínimo 4). Vagas que sobram viram BYE.
- Os cabeças de chave seguem a ordem padrão (1x16, 8x9, ...), então os BYEs ficam com os melhores seeds.
- Perdedores da upper caem na lower em ordem INVERTIDA para não repetir o confronto da upper logo em seguida.
- Grande final em série única (sem reset de chave).
"""
import math, secrets
from datetime import datetime
from web.extensions import db
from web.models import Match, MatchMap, VetoAction, PlayerMapStat

BYE = 'BYE'


def seed_order(size):
    order = [1]
    while len(order) < size:
        n = len(order) * 2
        order = [x for s in order for x in (s, n + 1 - s)]
    return order


def bracket_size(team_count):
    size = 4
    while size < team_count: size *= 2
    return size


def upper_round_name(r, k):
    return {k: 'Final da Upper', k - 1: 'Semifinal da Upper', k - 2: 'Quartas da Upper'}.get(r, f'Upper · Rodada {r}')


def lower_round_name(l, last):
    return {last: 'Final da Lower', last - 1: 'Semifinal da Lower'}.get(l, f'Lower · Rodada {l}')


def match_code(m):
    if m.bracket == 'FINAL': return 'GF'
    return f"{'U' if m.bracket == 'UPPER' else 'L'}{m.round}.{(m.position or 0) + 1}"


def clear_bracket(tournament):
    ids = [m.id for m in Match.query.filter_by(tournament_id=tournament.id).all()]
    if ids:
        for model in (PlayerMapStat, VetoAction, MatchMap):
            model.query.filter(model.match_id.in_(ids)).delete(synchronize_session=False)
        Match.query.filter(Match.id.in_(ids)).delete(synchronize_session=False)
    db.session.flush()


def generate(tournament, teams):
    """Cria todas as partidas. `teams` já vem na ordem de seed (índice 0 = seed 1)."""
    n = len(teams)
    if n < 2: raise ValueError('São necessários pelo menos 2 times confirmados.')
    clear_bracket(tournament)
    size = bracket_size(n); k = int(math.log2(size)); lower_last = 2 * (k - 1)
    bo = lambda default: default or 1

    def new(bracket, rnd, pos, label, best_of):
        m = Match(tournament_id=tournament.id, bracket=bracket, round=rnd, position=pos, label=label, best_of=best_of,
                  status='WAITING', config_token=secrets.token_urlsafe(24))
        db.session.add(m); return m

    upper = {r: [new('UPPER', r, i, upper_round_name(r, k), bo(tournament.bo_upper_final) if r == k else bo(tournament.bo_default))
                 for i in range(size >> r)] for r in range(1, k + 1)}
    lower_counts = {1: size // 4}
    for r in range(2, k + 1):
        lower_counts[2 * r - 2] = size >> r
        if r < k: lower_counts[2 * r - 1] = size >> (r + 1)
    lower = {l: [new('LOWER', l, i, lower_round_name(l, lower_last), bo(tournament.bo_lower_final) if l == lower_last else bo(tournament.bo_default))
                 for i in range(c)] for l, c in sorted(lower_counts.items())}
    final = new('FINAL', 1, 0, 'Grande final', bo(tournament.bo_grand_final))
    db.session.flush()

    def link_win(src, dst, slot):
        src.next_match_id, src.next_slot = dst.id, slot
        setattr(dst, f'team{slot}_from', f'W:{src.id}')

    def link_lose(src, dst, slot):
        src.loser_match_id, src.loser_slot = dst.id, slot
        setattr(dst, f'team{slot}_from', f'L:{src.id}')

    for r in range(1, k + 1):
        for i, m in enumerate(upper[r]):
            if r < k: link_win(m, upper[r + 1][i // 2], i % 2 + 1)
            else: link_win(m, final, 1)
            if r == 1: link_lose(m, lower[1][i // 2], i % 2 + 1)
            else:
                drop = lower[2 * r - 2]
                link_lose(m, drop[len(drop) - 1 - i], 2)  # cruzado/invertido
    for l, matches in lower.items():
        for i, m in enumerate(matches):
            if l == lower_last: link_win(m, final, 2)
            elif l == 1 or l % 2 == 1: link_win(m, lower[l + 1][i], 1)   # vencedor vai enfrentar quem cai da upper
            else: link_win(m, lower[l + 1][i // 2], i % 2 + 1)          # rodada de consolidação

    order = seed_order(size)
    for i, m in enumerate(upper[1]):
        for slot, seed in ((1, order[2 * i]), (2, order[2 * i + 1])):
            if seed <= n:
                setattr(m, f'team{slot}_id', teams[seed - 1].id); setattr(m, f'team{slot}_from', f'S:{seed}')
            else:
                setattr(m, f'team{slot}_from', BYE)
    db.session.flush()
    for m in upper[1]: check(m)
    db.session.flush()
    return size


def slot_state(m, slot):
    if getattr(m, f'team{slot}_id'): return 'TEAM'
    return BYE if getattr(m, f'team{slot}_from') == BYE else 'PENDING'


def _set_slot(m, slot, team_id):
    setattr(m, f'team{slot}_id', team_id)
    if not team_id: setattr(m, f'team{slot}_from', BYE)


def check(m):
    """Atualiza o estado da partida quando um lado é preenchido. Resolve BYEs automaticamente."""
    if m.status == 'FINISHED': return
    s1, s2 = slot_state(m, 1), slot_state(m, 2)
    if 'PENDING' in (s1, s2): return
    if s1 == s2 == 'TEAM':
        if m.status in ('WAITING', 'SCHEDULED', None): m.status = 'READY'
        return
    winner = m.team1_id if s1 == 'TEAM' else m.team2_id if s2 == 'TEAM' else None
    m.walkover = True
    finish(m, winner)


def finish(m, winner_id, walkover=None):
    m.winner_id = winner_id; m.status = 'FINISHED'; m.finished_at = datetime.utcnow()
    if walkover is not None: m.walkover = walkover
    loser_id = m.loser_id if winner_id else None
    if m.next_match_id:
        nxt = db.session.get(Match, m.next_match_id); _set_slot(nxt, m.next_slot, winner_id); check(nxt)
    if m.loser_match_id:
        lm = db.session.get(Match, m.loser_match_id); _set_slot(lm, m.loser_slot, loser_id); check(lm)


def can_reopen(m):
    for mid, slot in ((m.next_match_id, m.next_slot), (m.loser_match_id, m.loser_slot)):
        if not mid: continue
        nxt = db.session.get(Match, mid)
        if nxt.status not in ('WAITING', 'READY') or VetoAction.query.filter_by(match_id=nxt.id).first():
            return False
    return True


def reopen(m):
    """Desfaz o resultado (só se as partidas seguintes ainda não começaram)."""
    if not can_reopen(m): raise ValueError('As partidas seguintes já começaram; não dá para desfazer este resultado.')
    for mid, slot, kind in ((m.next_match_id, m.next_slot, 'W'), (m.loser_match_id, m.loser_slot, 'L')):
        if not mid: continue
        nxt = db.session.get(Match, mid)
        setattr(nxt, f'team{slot}_id', None); setattr(nxt, f'team{slot}_from', f'{kind}:{m.id}')
        nxt.status = 'WAITING'; nxt.winner_id = None; nxt.walkover = False
    m.winner_id = None; m.finished_at = None; m.walkover = False
    m.status = 'READY' if m.team1_id and m.team2_id else 'WAITING'


def describe_source(src, by_id):
    """Texto para um lado ainda vazio: 'Vencedor de U1.3', 'Perdedor de U2.1'."""
    if not src: return 'A definir'
    if src == BYE: return 'BYE'
    kind, _, ref = src.partition(':')
    if kind == 'S': return f'Seed {ref}'
    other = by_id.get(int(ref)) if ref.isdigit() else None
    code = match_code(other) if other else '?'
    return f"{'Vencedor' if kind == 'W' else 'Perdedor'} de {code}"


def columns(tournament):
    """Partidas agrupadas por coluna para desenhar a chave."""
    ms = Match.query.filter_by(tournament_id=tournament.id).filter(Match.bracket.isnot(None)).order_by(Match.round, Match.position).all()
    upper, lower, final = {}, {}, None
    for m in ms:
        if m.bracket == 'UPPER': upper.setdefault(m.round, []).append(m)
        elif m.bracket == 'LOWER': lower.setdefault(m.round, []).append(m)
        else: final = m
    return [upper[r] for r in sorted(upper)], [lower[r] for r in sorted(lower)], final, {m.id: m for m in ms}
