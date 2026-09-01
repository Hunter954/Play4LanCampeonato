import re
import socket
import subprocess
import time

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


class CS2Process:
    def __init__(self, cfg):
        self.cfg = cfg
        self.process = None

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
        if self.process and self.process.poll() is None:
            return 'ONLINE'
        # Se o Agent reiniciar enquanto o CS2 continuar aberto, não perdemos o
        # estado do painel: o RCON/porta local confirma que o processo existe.
        return 'ONLINE' if self._port_open() else 'OFFLINE'

    def start(self):
        if self.status == 'ONLINE':
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
        if self.status != 'ONLINE':
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
        if self.status != 'ONLINE':
            return {'online': False, 'rcon_ok': False, 'players': [], 'player_count': 0}
        result = self.rcon('status')
        if not result['ok']:
            return {
                'online': True,
                'rcon_ok': False,
                'rcon_error': result.get('error'),
                'players': [],
                'player_count': 0,
            }
        parsed = parse_status(result.get('result', ''))
        parsed.update({'online': True, 'rcon_ok': True})
        return parsed

    def execute(self, command, payload):
        if command == 'START':
            return self.start()
        if command == 'STOP':
            return self.stop()
        if command == 'RESTART':
            return self.restart()
        if command == 'RCON':
            raw = (payload or {}).get('command', '').strip()
            if not raw:
                return {'ok': False, 'error': 'Comando RCON vazio.'}
            return self.rcon(raw)
        return {'ok': False, 'error': f'Comando não suportado pelo Agent: {command}'}
