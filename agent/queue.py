import sqlite3, json, uuid
class OfflineQueue:
    def __init__(self,path='agent_queue.db'):
        self.db=sqlite3.connect(path,check_same_thread=False); self.db.execute('create table if not exists events(id integer primary key, event_uuid text unique, body text, sent integer default 0)'); self.db.commit()
    def add(self,event_type,payload=None,server_id=None,match_id=None):
        e={'event_uuid':str(uuid.uuid4()),'event_type':event_type,'payload':payload or {},'server_id':server_id,'match_id':match_id}; self.db.execute('insert or ignore into events(event_uuid,body) values(?,?)',(e['event_uuid'],json.dumps(e))); self.db.commit(); return e
    def pending(self,limit=100): return [(r[0],json.loads(r[1])) for r in self.db.execute('select id,body from events where sent=0 order by id limit ?',(limit,)).fetchall()]
    def mark_sent(self,ids):
        if ids: self.db.executemany('update events set sent=1 where id=?',[(i,) for i in ids]); self.db.commit()
