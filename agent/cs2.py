import subprocess, os, signal
class CS2Process:
    def __init__(self,cfg): self.cfg=cfg; self.process=None
    @property
    def status(self): return 'ONLINE' if self.process and self.process.poll() is None else 'OFFLINE'
    def start(self):
        if self.status=='ONLINE': return True
        self.process=subprocess.Popen([self.cfg['exe'],*self.cfg.get('args',[])],cwd=self.cfg.get('cwd') or None,creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)); return True
    def stop(self):
        if self.status!='ONLINE': return True
        self.process.terminate()
        try:self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:self.process.kill()
        return True
    def restart(self): self.stop(); return self.start()
    def execute(self,command,payload):
        if command=='START': return self.start()
        if command=='STOP': return self.stop()
        if command=='RESTART': return self.restart()
        # LOAD_MATCH / RCON / RESTORE serão ligados ao adaptador escolhido para CS2.
        return False
