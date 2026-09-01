"""Estado efêmero de telemetria para o painel em tempo real.

O Railway roda o web app com um worker (Procfile), então este cache evita gravar
um MatchEvent a cada poucos segundos só para manter o dashboard vivo. O banco
continua recebendo snapshots periódicos como fallback/histórico.
"""
from copy import deepcopy

_SERVER_STATE = {}


def set_server_state(code, state):
    _SERVER_STATE[code] = deepcopy(state or {})


def get_server_state(code):
    state = _SERVER_STATE.get(code)
    return deepcopy(state) if state is not None else None
