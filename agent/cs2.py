import subprocess
import re
from agent.rcon import RCONClient, RCONError


_PLAYER_PATTERNS = [
    # Formatos que aparecem em variantes do Source/CS2 status.
    re.compile(r'^#\s*(?P<userid>\d+)\s+(?P<slot>\d+)\s+"(?P<name>.*?)"\s+(?P<steam>\S+)\s+(?P<connected>\S+)\s+(?P<ping>\d+)\s+(?P<loss>\d+)\s+(?P<state>\S+)', re.I),
    re.compile(r'^#\s*(?P<userid>\d+)\s+"(?P<name>.*?)"\s+(?P<steam>\S+)\s+(?P<connected>\S+)\s+(?P<ping>\d+)\s+(?P<loss>\d+)\s+(?P<state>\S+)', re.I),
]


def parse_status(text: str) -> dict:
    data = {'raw': text or '', 'players': []}
    for raw_line in (text or '').splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if lower.startswith('hostname') and ':' in line:
            data['hostname'] = line.split(':', 1)[1].strip()
        elif lower.startswith('map') and ':' in line:
            data['map'] = line.split(':', 1)[1].strip().split()[0]
        elif lower.startswith('players') and ':' in line:
            data['players_summary'] = line.split(':', 1)[1].strip()
        for pattern in _PLAYER_PATTERNS:
            match = pattern.match(line)
            if match:
                player = match.groupdict()
                try:
                    player['userid'] = int(player['userid'])
                    player['ping'] = int(player['ping'])
                    player['loss'] = int(player['loss'])
                except (TypeError, ValueError):
                    pass
                data['players'].append(player)
                break
    data['player_count'] = len(data['players'])
    return data


class CS2Process:
    def __init__(self, cfg):
        self.cfg = cfg
        self.process = None

    @property
    def status(self):
        return 'ONLINE' if self.process and self.process.poll() is None else 'OFFLINE'

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
        self.process.terminate()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.kill()
        return {'ok': True, 'result': 'Servidor parado.'}

    def restart(self):
        stopped = self.stop()
        if not stopped['ok']:
            return stopped
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
            return {'online': False, 'players': [], 'player_count': 0}
        result = self.rcon('status')
        if not result['ok']:
            return {'online': True, 'rcon_ok': False, 'rcon_error': result.get('error'), 'players': [], 'player_count': 0}
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
