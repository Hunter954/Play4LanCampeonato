import json, time, threading, pathlib
from agent.client import PlatformClient
from agent.cs2 import CS2Process
from agent.queue import OfflineQueue

def load_cfg():
    p=pathlib.Path('agent/config.json')
    if not p.exists(): raise SystemExit('Copie agent/config.example.json para agent/config.json e configure.')
    return json.loads(p.read_text(encoding='utf8'))

def main():
    cfg=load_cfg(); client=PlatformClient(cfg['platform_url'],cfg['token']); queue=OfflineQueue(); servers={x['code']:CS2Process(x) for x in cfg['servers']}
    last_hb=0
    print('CS2 Platform Agent:',cfg['host_id'])
    while True:
        now=time.time()
        try:
            if now-last_hb>=cfg.get('heartbeat_seconds',10):
                client.heartbeat({'host_id':cfg['host_id'],'servers':[{'code':code,'display_name':p.cfg.get('display_name',code),'status':p.status} for code,p in servers.items()]}); last_hb=now
            rows=queue.pending();
            if rows: client.send_events([e for _,e in rows]); queue.mark_sent([i for i,_ in rows])
            for c in client.commands(cfg['host_id']):
                p=servers.get(c.get('server_code')); ok=bool(p and p.execute(c['command'],c.get('payload',{}))); client.ack(c['id'],'DONE' if ok else 'FAILED')
        except Exception as e: print('offline/erro:',e)
        time.sleep(cfg.get('command_poll_seconds',2))
if __name__=='__main__': main()
