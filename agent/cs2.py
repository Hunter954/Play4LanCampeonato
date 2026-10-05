import json
import pathlib
import re
import socket
import subprocess
import threading
import time

from agent import updater
from agent.rcon import RCONClient, RCONError


# Mantemos os parsers conhecidos e acrescentamos um parser tolerante para as
# variações de `status` que o CS2 vem apresentando entre builds.
_PLAYER_PATTERNS = [
    re.compile(r'^#\s*(?P<userid>\d+)\s+(?P<slot>\d+)\s+"(?P<name>.*?)"\s+(?P<steam>\S+)\s+(?P<connected>\S+)\s+(?P<ping>\d+)\s+(?P<loss>\d+)\s+(?P<state>\S+)', re.I),
    re.compile(r'^#\s*(?P<userid>\d+)\s+"(?P<name>.*?)"\s+(?P<steam>\S+)\s+(?P<connected>\S+)\s+(?P<ping>\d+)\s+(?P<loss>\d+)\s+(?P<state>\S+)', re.I),
]


def _int_or(value, fallback=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _looks_like_steam(value: str) -> bool:
    upper = (value or '').upper()
    return (
        upper.startswith('STEAM_')
        or upper.startswith('[U:')
        or upper == 'BOT'
        or (value.isdigit() and len(value) >= 15)
    )


def _parse_player_fallback(line: str):
    # Exemplo comum:
    # # 2 1 "nickname" STEAM_1:0:123 00:15 18 0 active ...
    match = re.match(r'^#\s*(?P<userid>\d+)\s+(?:(?P<slot>\d+)\s+)?"(?P<name>.*?)"\s+(?P<rest>.*)$', line)
    if not match:
        return None

    rest = match.group('rest').split()
    if not rest:
        return None

    steam_index = next((i for i, token in enumerate(rest) if _looks_like_steam(token)), None)
    if steam_index is None:
        return None

    steam = rest[steam_index]
    tail = rest[steam_index + 1:]
    connected = tail[0] if tail else '?'

    # Em geral ping/loss são os dois números seguintes ao tempo conectado.
    numeric_tail = [(i, token) for i, token in enumerate(tail[1:], start=1) if token.isdigit()]
    ping = _int_or(numeric_tail[0][1], '?') if numeric_tail else '?'
    loss = _int_or(numeric_tail[1][1], '?') if len(numeric_tail) > 1 else '?'

    state = '?'
    for token in tail:
        if token.lower() in {'active', 'spawning', 'challenging', 'connected', 'zombie'}:
            state = token
            break

    return {
        'userid': int(match.group('userid')),
        'slot': _int_or(match.group('slot')),
        'name': match.group('name'),
        'steam': steam,
        'connected': connected,
        'ping': ping,
        'loss': loss,
        'state': state,
    }


def parse_status(text: str) -> dict:
    data = {'raw': text or '', 'players': []}
    seen_userids = set()

    for raw_line in (text or '').splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if lower.startswith('hostname') and ':' in line:
            data['hostname'] = line.split(':', 1)[1].strip()
        elif lower.startswith('map') and ':' in line:
            data['map'] = line.split(':', 1)[1].strip().split()[0]
        elif lower.startswith('players') and ':' in line:
            data['players_summary'] = line.split(':', 1)[1].strip()

        player = None
        for pattern in _PLAYER_PATTERNS:
            match = pattern.match(line)
            if match:
                player = match.groupdict()
                player['userid'] = _int_or(player.get('userid'), player.get('userid'))
                player['slot'] = _int_or(player.get('slot'), player.get('slot'))
                player['ping'] = _int_or(player.get('ping'), player.get('ping'))
                player['loss'] = _int_or(player.get('loss'), player.get('loss'))
                break

        if player is None and line.startswith('#'):
            player = _parse_player_fallback(line)

        if player and player.get('userid') not in seen_userids:
            seen_userids.add(player.get('userid'))
            data['players'].append(player)

    data['player_count'] = len(data['players'])
    return data


def parse_play4lan_players(text: str):
    marker = 'PLAY4LAN_PLAYERS_JSON '
    raw = text or ''
    idx = raw.find(marker)
    if idx < 0:
        return None
    payload = raw[idx + len(marker):].strip()
    # Algumas implementações RCON podem acrescentar uma nova linha depois da resposta.
    first_line = payload.splitlines()[0].strip() if payload else ''
    if not first_line:
        return []
    try:
        rows = json.loads(first_line)
    except json.JSONDecodeError:
        # Tenta decodificar só o primeiro objeto JSON válido.
        try:
            rows, _ = json.JSONDecoder().raw_decode(payload)
        except json.JSONDecodeError:
            return None
    if not isinstance(rows, list):
        return None
    players = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        players.append({
            'userid': _int_or(row.get('userid'), row.get('userid')),
            'name': row.get('name') or '?',
            'steam_id64': str(row.get('steam_id64') or ''),
            'steam': str(row.get('steam_id64') or ''),
            'team_num': _int_or(row.get('team_num'), 1),
            'team': row.get('team') or 'SPEC',
            'team_name': row.get('team_name') or 'ESPECTADOR',
            'ready': bool(row.get('ready')),
            'ping': '?',
        })
    return players



def parse_play4lan_state(text: str):
    marker = 'PLAY4LAN_STATE_JSON '
    raw = text or ''
    idx = raw.find(marker)
    if idx < 0:
        return None
    payload = raw[idx + len(marker):].strip()
    try:
        state, _ = json.JSONDecoder().raw_decode(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(state, dict):
        return None
    players = state.get('players') if isinstance(state.get('players'), list) else []
    state['players'] = players
    state['player_count'] = len(players)
    state['player_source'] = 'play4lan_state'
    state['play4lan_plugin_ok'] = True
    return state


def merge_player_sources(structured, status_players):
    status_players = status_players or []
    by_userid = {str(p.get('userid')): p for p in status_players if p.get('userid') is not None}
    merged = []
    for player in structured or []:
        status = by_userid.get(str(player.get('userid'))) or {}
        item = dict(player)
        if status.get('ping') not in (None, '?'):
            item['ping'] = status.get('ping')
        if status.get('connected'):
            item['connected'] = status.get('connected')
        if status.get('state'):
            item['state'] = status.get('state')
        merged.append(item)
    return merged


class CS2Process:
    def __init__(self, cfg, global_cfg=None):
        self.cfg = cfg
        self.process = None
        g = global_cfg or {}
        exe = pathlib.Path(cfg.get('exe', ''))
        # .../runtime/server01/game/bin/win64/cs2.exe -> .../runtime/server01
        self.install_dir = cfg.get('install_dir') or (str(exe.parents[3]) if len(exe.parents) > 3 else '')
        self.steamcmd = cfg.get('steamcmd') or g.get('steamcmd') or str(pathlib.Path(self.install_dir).parent / 'steamcmd' / 'steamcmd.exe')
        self.auto_update = bool(cfg.get('auto_update', g.get('auto_update', False)))
        self.version = {'installed': None, 'required': None, 'up_to_date': None, 'checked_at': None, 'error': None}
        self.update = {'state': 'IDLE', 'message': '', 'started_at': None, 'finished_at': None, 'log': [], 'trigger': None}
        self._last_check = 0.0

    # ---------- versão e atualização ----------
    def check_version(self, force=False):
        if not force and time.time() - self._last_check < updater.CHECK_EVERY: return self.version
        self._last_check = time.time()
        installed = updater.installed_version(self.install_dir)
        self.version.update({'installed': installed, 'checked_at': int(time.time())})
        if not installed:
            self.version['error'] = 'steam.inf não encontrado'; return self.version
        try:
            res = updater.check_valve(installed)
            self.version.update({'up_to_date': res['up_to_date'], 'required': res['required'], 'error': None})
        except Exception as exc:  # sem internet / Valve fora: mantém o último resultado
            self.version['error'] = f'Falha ao consultar a Valve: {exc}'
        return self.version

    @property
    def updating(self): return self.update['state'] == 'RUNNING'

    def _log(self, line):
        self.update['log'] = (self.update['log'] + [line])[-40:]
        self.update['message'] = line[:200]

    def start_update(self, trigger='manual'):
        if self.updating: return {'ok': True, 'result': 'Atualização já em andamento.'}
        if not pathlib.Path(self.steamcmd).exists():
            return {'ok': False, 'error': f'SteamCMD não encontrado em {self.steamcmd}. Configure "steamcmd" no config.json.'}
        self.update = {'state': 'RUNNING', 'message': 'Preparando atualização...', 'started_at': int(time.time()), 'finished_at': None, 'log': [], 'trigger': trigger}
        threading.Thread(target=self._do_update, daemon=True).start()
        return {'ok': True, 'result': 'Atualização iniciada. Acompanhe o progresso no painel.'}

    def _do_update(self):
        was_running = self._process_alive() or self._port_open()
        try:
            if was_running:
                self._log('Desligando o servidor para atualizar...')
                stopped = self.stop()
                if not stopped.get('ok'): raise RuntimeError(stopped.get('error') or 'Não foi possível desligar o servidor.')
            self._log('Rodando SteamCMD (app_update 730 validate)...')
            if not updater.run_steamcmd(self.steamcmd, self.install_dir, self._log):
                raise RuntimeError('SteamCMD terminou com erro. Veja o log.')
            if updater.ensure_metamod(self.install_dir): self._log('gameinfo.gi corrigido: Metamod recolocado.')
            self.check_version(force=True)
            if was_running:
                self._log('Ligando o servidor novamente...')
                self.start()
            self.update.update({'state': 'DONE', 'finished_at': int(time.time()),
                                'message': f"Atualizado para {self.version.get('installed') or '?'}" + (' e religado.' if was_running else '.')})
        except Exception as exc:
            self.update.update({'state': 'FAILED', 'finished_at': int(time.time()), 'message': str(exc)[:200]})

    def maybe_auto_update(self, player_count, busy):
        """Atualiza sozinho quando a Valve exige e o servidor está vazio e sem partida."""
        if not self.auto_update or self.updating or self.version.get('up_to_date') is not False: return False
        if player_count or busy: return False
        if self.update['state'] == 'FAILED' and time.time() - (self.update.get('finished_at') or 0) < 1800: return False
        self.start_update('auto'); return True

    def _process_alive(self): return bool(self.process and self.process.poll() is None)

    def _port_open(self):
        host = self.cfg.get('rcon_host', '127.0.0.1')
        port = int(self.cfg.get('rcon_port', self._game_port()))
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return True
        except OSError:
            return False

    @property
    def status(self):
        if self.updating:
            return 'UPDATING'
        port = self._port_open()
        if self._process_alive():
            # Processo aberto mas o RCON ainda não responde: o CS2 está carregando.
            return 'ONLINE' if port else 'STARTING'
        # Se o Agent reiniciar enquanto o CS2 continuar aberto, o RCON/porta local
        # confirma que o processo existe.
        return 'ONLINE' if port else 'OFFLINE'

    def start(self):
        if self.status in ('ONLINE', 'STARTING'):
            return {'ok': True, 'result': 'Servidor já estava online.'}
        exe = self.cfg['exe']
        try:
            self.process = subprocess.Popen(
                [exe, *self.cfg.get('args', [])],
                cwd=self.cfg.get('cwd') or None,
                creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0),
            )
        except FileNotFoundError as exc:
            return {'ok': False, 'error': f'Arquivo/caminho não encontrado: {exc.filename or exe}'}
        return {'ok': True, 'result': f'Servidor iniciado. PID {self.process.pid}.'}

    def stop(self):
        if not self._process_alive() and not self._port_open():
            return {'ok': True, 'result': 'Servidor já estava offline.'}

        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
            return {'ok': True, 'result': 'Servidor parado.'}

        # Processo já existia antes do Agent/reinício do Agent. Tenta encerrar
        # de forma limpa via RCON em vez de deixar o painel sem controle.
        try:
            RCONClient(
                host=self.cfg.get('rcon_host', '127.0.0.1'),
                port=self.cfg.get('rcon_port', self._game_port()),
                password=self.cfg.get('rcon_password', ''),
                timeout=self.cfg.get('rcon_timeout', 2.5),
            ).command('quit')
            for _ in range(20):
                if not self._port_open():
                    break
                time.sleep(0.25)
            return {'ok': True, 'result': 'Servidor externo parado via RCON.'}
        except (RCONError, OSError) as exc:
            return {'ok': False, 'error': f'Não foi possível parar o processo externo: {exc}'}

    def restart(self):
        stopped = self.stop()
        if not stopped['ok']:
            return stopped
        time.sleep(0.5)
        return self.start()

    def rcon(self, command):
        try:
            output = RCONClient(
                host=self.cfg.get('rcon_host', '127.0.0.1'),
                port=self.cfg.get('rcon_port', self._game_port()),
                password=self.cfg.get('rcon_password', ''),
                timeout=self.cfg.get('rcon_timeout', 2.5),
            ).command(command)
            return {'ok': True, 'result': output}
        except (RCONError, OSError) as exc:
            return {'ok': False, 'error': str(exc)}

    def _game_port(self):
        args = self.cfg.get('args', [])
        for i, arg in enumerate(args):
            if arg == '-port' and i + 1 < len(args):
                try:
                    return int(args[i + 1])
                except ValueError:
                    pass
        return 27015

    def telemetry(self):
        data = self._telemetry()
        data['version'] = dict(self.version)
        data['update'] = {k: v for k, v in self.update.items() if k != 'log'}
        data['update']['log'] = self.update['log'][-12:]
        data['auto_update'] = self.auto_update
        return data

    def _telemetry(self):
        if self.status != 'ONLINE':
            return {'online': False, 'rcon_ok': False, 'players': [], 'player_count': 0, 'player_source': 'offline'}

        # Fonte principal 1.0.6: estado completo estruturado do plugin.
        state_result = self.rcon('css_play4lan_state')
        state_data = parse_play4lan_state(state_result.get('result', '')) if state_result.get('ok') else None
        if state_data is not None:
            state_data.update({'online': True, 'rcon_ok': True})
            return state_data

        # Compatibilidade com 1.0.4/1.0.5.
        status_result = self.rcon('status')
        status_data = parse_status(status_result.get('result', '')) if status_result.get('ok') else {'players': [], 'player_count': 0}
        play4lan_result = self.rcon('css_play4lan_players')
        structured_players = parse_play4lan_players(play4lan_result.get('result', '')) if play4lan_result.get('ok') else None
        if structured_players is not None:
            status_data['players'] = merge_player_sources(structured_players, status_data.get('players', []))
            status_data['player_count'] = len(status_data['players'])
            status_data['player_source'] = 'play4lan_plugin'
            status_data['play4lan_plugin_ok'] = True
        else:
            status_data['player_source'] = 'status_fallback'
            status_data['play4lan_plugin_ok'] = False
        status_data.update({'online': True, 'rcon_ok': bool(status_result.get('ok') or play4lan_result.get('ok'))})
        if not status_data['rcon_ok']:
            status_data['rcon_error'] = status_result.get('error') or play4lan_result.get('error') or state_result.get('error')
        return status_data

    def execute(self, command, payload):
        if command == 'START':
            return self.start()
        if command == 'STOP':
            return self.stop()
        if command == 'RESTART':
            return self.restart()
        if command == 'UPDATE':
            return self.start_update('manual')
        if command == 'CHECK_UPDATE':
            v = self.check_version(force=True)
            if v.get('error'): return {'ok': False, 'error': v['error']}
            return {'ok': True, 'result': 'Atualizado.' if v.get('up_to_date') else f"Atualização disponível: {v.get('required')}"}
        if command == 'RCON':
            raw = (payload or {}).get('command', '').strip()
            if not raw:
                return {'ok': False, 'error': 'Comando RCON vazio.'}
            return self.rcon(raw)
        return {'ok': False, 'error': f'Comando não suportado pelo Agent: {command}'}
