import json
import time
import pathlib
from agent.client import PlatformClient
from agent.cs2 import CS2Process
from agent.queue import OfflineQueue


def load_cfg():
    p = pathlib.Path('agent/config.json')
    if not p.exists():
        raise SystemExit('Copie agent/config.example.json para agent/config.json e configure.')
    return json.loads(p.read_text(encoding='utf8'))


def main():
    cfg = load_cfg()
    client = PlatformClient(cfg['platform_url'], cfg['token'])
    queue = OfflineQueue()
    servers = {x['code']: CS2Process(x) for x in cfg['servers']}
    last_hb = 0
    print('CS2 Platform Agent:', cfg['host_id'])

    while True:
        now = time.time()
        try:
            if now - last_hb >= cfg.get('heartbeat_seconds', 10):
                server_rows = []
                for code, process in servers.items():
                    telemetry = process.telemetry()
                    server_rows.append({
                        'code': code,
                        'display_name': process.cfg.get('display_name', code),
                        'status': process.status,
                        'telemetry': telemetry,
                    })
                client.heartbeat({'host_id': cfg['host_id'], 'servers': server_rows})
                last_hb = now

            rows = queue.pending()
            if rows:
                client.send_events([event for _, event in rows])
                queue.mark_sent([event_id for event_id, _ in rows])

            for command in client.commands(cfg['host_id']):
                process = servers.get(command.get('server_code'))
                if not process:
                    outcome = {'ok': False, 'error': f"Servidor {command.get('server_code')} não existe no config.json local."}
                else:
                    outcome = process.execute(command['command'], command.get('payload', {}))
                status = 'DONE' if outcome.get('ok') else 'FAILED'
                client.ack(command['id'], status, result=outcome.get('result'), error=outcome.get('error'))
                label = f"{command.get('server_code')} {command.get('command')}"
                print(f"{label} -> {status}" + (f": {outcome.get('error')}" if outcome.get('error') else ''))
        except Exception as exc:
            print('offline/erro:', exc)
        time.sleep(cfg.get('command_poll_seconds', 2))


if __name__ == '__main__':
    main()
