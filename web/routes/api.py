import os, uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, abort, redirect
from web.extensions import db, socketio
from web.models import Server, ServerCommand, MatchEvent, Demo
from web.storage import upload_fileobj, presigned_download
bp=Blueprint('api',__name__,url_prefix='/api/v1')
def auth_agent():
    if request.headers.get('Authorization') != 'Bearer '+os.getenv('AGENT_SHARED_TOKEN',''): abort(401)
@bp.post('/agent/heartbeat')
def heartbeat():
    auth_agent(); data=request.get_json(force=True); host=data['host_id']
    for s in data.get('servers',[]):
        row=Server.query.filter_by(code=s['code']).first()
        if not row: row=Server(code=s['code']); db.session.add(row)
        row.host_id=host; row.display_name=s.get('display_name',s['code']); row.status=s.get('status','UNKNOWN'); row.last_heartbeat=datetime.utcnow()
    db.session.commit(); return jsonify(ok=True)
@bp.get('/agent/commands/<host_id>')
def commands(host_id):
    auth_agent(); rows=ServerCommand.query.filter_by(host_id=host_id,status='PENDING').order_by(ServerCommand.id).limit(50).all(); return jsonify(commands=[{'id':x.id,'server_code':x.server_code,'command':x.command,'payload':x.payload} for x in rows])
@bp.post('/agent/commands/<int:cid>/ack')
def ack(cid):
    auth_agent(); c=ServerCommand.query.get_or_404(cid); c.status=request.json.get('status','DONE'); c.completed_at=datetime.utcnow(); db.session.commit(); return jsonify(ok=True)
@bp.post('/agent/events')
def events():
    auth_agent(); items=request.get_json(force=True).get('events',[]); added=0
    for e in items:
        if MatchEvent.query.filter_by(event_uuid=e['event_uuid']).first(): continue
        db.session.add(MatchEvent(event_uuid=e['event_uuid'],server_id=e.get('server_id'),match_id=e.get('match_id'),event_type=e['event_type'],payload=e.get('payload',{}))); added+=1
        socketio.emit('match_event',e)
    db.session.commit(); return jsonify(ok=True,added=added)
@bp.post('/agent/demos')
def demo_upload():
    auth_agent(); f=request.files['file']; match_id=request.form.get('match_id',type=int); map_name=request.form.get('map_name'); part=request.form.get('part_number',1,type=int)
    key=f'demos/{match_id or "unknown"}/{uuid.uuid4().hex}_{f.filename}'; storage=upload_fileobj(f.stream,key)
    if not storage:
        import pathlib; p=pathlib.Path('instance/uploads')/key; p.parent.mkdir(parents=True,exist_ok=True); f.stream.seek(0); p.write_bytes(f.stream.read()); storage='local:'+str(p)
    d=Demo(match_id=match_id,map_name=map_name,part_number=part,filename=f.filename,storage_key=storage,size_bytes=request.content_length); db.session.add(d); db.session.commit(); return jsonify(ok=True,id=d.id)
@bp.get('/demos/<int:did>/download')
def demo_download(did):
    d=Demo.query.get_or_404(did)
    if d.storage_key and d.storage_key.startswith('local:'):
        from flask import send_file; return send_file(d.storage_key[6:],as_attachment=True,download_name=d.filename)
    u=presigned_download(d.storage_key)
    if not u: abort(404)
    return redirect(u)
