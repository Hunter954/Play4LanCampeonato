import json
import pathlib
import time

from agent.client import PlatformClient
from agent.cs2 import CS2Process
from agent.queue import OfflineQueue

AGENT_VERSION = '1.1.0'


def load_cfg():
    path = pathlib.Path('agent/config.json')
    if not path.exists():
        raise SystemExit('Copie agent/config.example.json para agent/config.json e configure.')
    return json.loads(path.read_text(encoding='utf8'))


def build_heartbeat(cfg, servers):
    rows = []
    for code, process in servers.items():
        process.check_version()  # consulta a Valve no máximo a cada 5 min
        telemetry = process.telemetry()
        process.last_player_count = int(telemetry.get('player_count') or 0)
        rows.append({
            'code': code,
            'display_name': process.cfg.get('display_name', code),
            'status': process.status,
            'telemetry': telemetry,
        })
    return {'host_id': cfg['host_id'], 'agent_version': AGENT_VERSION, 'servers': rows}


def send_heartbeat(client, cfg, servers):
    reply = client.heartbeat(build_heartbeat(cfg, servers)) or {}
    # O painel manda as preferências de cada servidor (atualização automática) e se há partida em andamento.
    for code, settings in (reply.get('settings') or {}).items():
        process = servers.get(code)
        if not process: continue
        if 'auto_update' in settings: process.auto_update = bool(settings['auto_update'])
        if process.maybe_auto_update(getattr(process, 'last_player_count', 0), bool(settings.get('busy'))):
            print(f'{code}: atualização automática iniciada (versão exigida pela Valve: {process.version.get("required")})')


def main():
    cfg = load_cfg()
    client = PlatformClient(cfg['platform_url'], cfg['token'])
    queue = OfflineQueue()
    servers = {item['code']: CS2Process(item, cfg) for item in cfg['servers']}

    # Para o painel parecer realmente vivo, limitamos o intervalo máximo a 3s.
    # heartbeat_seconds continua podendo reduzir esse valor no config.json.
    heartbeat_seconds = max(1.0, min(float(cfg.get('heartbeat_seconds', 3)), 3.0))
    command_poll_seconds = max(0.5, min(float(cfg.get('command_poll_seconds', 1)), 2.0))
    last_hb = 0.0

    print(f"PLAY4LAN Agent {AGENT_VERSION}:", cfg['host_id'])
    for code, process in servers.items():
        print(f'  {code}: instalação {process.install_dir} | SteamCMD {process.steamcmd}')
    print(f'Telemetria: {heartbeat_seconds:.1f}s | comandos: {command_poll_seconds:.1f}s')

    while True:
        now = time.time()
        try:
            if now - last_hb >= heartbeat_seconds:
                send_heartbeat(client, cfg, servers)
                last_hb = time.time()

            rows = queue.pending()
            if rows:
                client.send_events([event for _, event in rows])
                queue.mark_sent([event_id for event_id, _ in rows])

            commands = client.commands(cfg['host_id'])
            state_changed = False
            for command in commands:
                process = servers.get(command.get('server_code'))
                if not process:
                    outcome = {
                        'ok': False,
                        'error': f"Servidor {command.get('server_code')} não existe no config.json local.",
                    }
                else:
                    outcome = process.execute(command['command'], command.get('payload', {}))

                status = 'DONE' if outcome.get('ok') else 'FAILED'
                client.ack(
                    command['id'],
                    status,
                    result=outcome.get('result'),
                    error=outcome.get('error'),
                )
                label = f"{command.get('server_code')} {command.get('command')}"
                print(f"{label} -> {status}" + (f": {outcome.get('error')}" if outcome.get('error') else ''))
                state_changed = True

            # START/STOP/RESTART e qualquer RCON atualizam a página imediatamente,
            # sem esperar o próximo ciclo de heartbeat.
            if state_changed:
                send_heartbeat(client, cfg, servers)
                last_hb = time.time()

        except Exception as exc:
            print('offline/erro:', exc)

        time.sleep(command_poll_seconds)


if __name__ == '__main__':
    main()
