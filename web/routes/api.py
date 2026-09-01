import os
import uuid
from datetime import datetime

from flask import Blueprint, abort, jsonify, redirect, request

from web.extensions import db, socketio
from web.models import Demo, MatchEvent, Server, ServerCommand
from web.live_state import set_server_state
from web.player_identity import enrich_telemetry
from web.storage import presigned_download, upload_fileobj

bp = Blueprint('api', __name__, url_prefix='/api/v1')


def auth_agent():
    if request.headers.get('Authorization') != 'Bearer ' + os.getenv('AGENT_SHARED_TOKEN', ''):
        abort(401)


def _iso(value):
    return value.isoformat() + 'Z' if value else None


@bp.post('/agent/heartbeat')
def heartbeat():
    auth_agent()
    data = request.get_json(force=True)
    host = data['host_id']
    realtime_updates = []

    for server_data in data.get('servers', []):
        row = Server.query.filter_by(code=server_data['code']).first()
        if not row:
            row = Server(code=server_data['code'])
            db.session.add(row)

        row.host_id = host
        row.display_name = server_data.get('display_name', server_data['code'])
        row.status = server_data.get('status', 'UNKNOWN')
        row.last_heartbeat = datetime.utcnow()

        telemetry = enrich_telemetry(server_data.get('telemetry') or {})
        # O retorno bruto do comando status fica disponível no histórico RCON;
        # não precisamos trafegá-lo/gravar a cada heartbeat.
        telemetry.pop('raw', None)

        set_server_state(server_data['code'], {
            'status': row.status,
            'last_heartbeat': row.last_heartbeat,
            'telemetry': telemetry,
        })

        # Snapshot histórico limitado para não transformar telemetria de 3s em
        # milhares de linhas por hora no PostgreSQL.
        last_event = (
            MatchEvent.query
            .filter_by(server_id=server_data['code'], event_type='SERVER_STATUS')
            .order_by(MatchEvent.id.desc())
            .first()
        )
        if not last_event or (row.last_heartbeat - last_event.created_at).total_seconds() >= 15:
            db.session.add(MatchEvent(
                event_uuid=str(uuid.uuid4()),
                server_id=server_data['code'],
                match_id=row.current_match_id,
                event_type='SERVER_STATUS',
                payload=telemetry,
            ))
        realtime_updates.append((row, telemetry))

    db.session.commit()

    # Só publica depois do commit: a tela ao receber o evento já consegue
    # consultar a mesma informação pela API de fallback.
    for row, telemetry in realtime_updates:
        socketio.emit('server_status', {
            'server_id': row.code,
            'display_name': row.display_name or row.code,
            'host_id': row.host_id,
            'status': row.status,
            'last_heartbeat': _iso(row.last_heartbeat),
            'payload': telemetry,
        })

    return jsonify(ok=True)


@bp.get('/agent/commands/<host_id>')
def commands(host_id):
    auth_agent()
    rows = ServerCommand.query.filter_by(host_id=host_id, status='PENDING').order_by(ServerCommand.id).limit(50).all()
    return jsonify(commands=[{
        'id': command.id,
        'server_code': command.server_code,
        'command': command.command,
        'payload': command.payload,
    } for command in rows])


@bp.post('/agent/commands/<int:cid>/ack')
def ack(cid):
    auth_agent()
    command = ServerCommand.query.get_or_404(cid)
    body = request.get_json(silent=True) or {}
    command.status = body.get('status', 'DONE')
    payload = dict(command.payload or {})
    if body.get('result') is not None:
        payload['_result'] = body.get('result')
    if body.get('error') is not None:
        payload['_error'] = body.get('error')
    command.payload = payload
    command.completed_at = datetime.utcnow()
    db.session.commit()

    socketio.emit('server_command', {
        'id': command.id,
        'server_code': command.server_code,
        'command': command.command,
        'rcon_command': payload.get('command'),
        'status': command.status,
        'result': payload.get('_result'),
        'error': payload.get('_error'),
        'created_at': _iso(command.created_at),
        'completed_at': _iso(command.completed_at),
    })
    return jsonify(ok=True)


@bp.post('/agent/events')
def events():
    auth_agent()
    items = request.get_json(force=True).get('events', [])
    added = 0
    emitted = []
    for event_data in items:
        if MatchEvent.query.filter_by(event_uuid=event_data['event_uuid']).first():
            continue
        db.session.add(MatchEvent(
            event_uuid=event_data['event_uuid'],
            server_id=event_data.get('server_id'),
            match_id=event_data.get('match_id'),
            event_type=event_data['event_type'],
            payload=event_data.get('payload', {}),
        ))
        added += 1
        emitted.append(event_data)
    db.session.commit()
    for event_data in emitted:
        socketio.emit('match_event', event_data)
    return jsonify(ok=True, added=added)


@bp.post('/agent/demos')
def demo_upload():
    auth_agent()
    file = request.files['file']
    match_id = request.form.get('match_id', type=int)
    map_name = request.form.get('map_name')
    part = request.form.get('part_number', 1, type=int)
    key = f'demos/{match_id or "unknown"}/{uuid.uuid4().hex}_{file.filename}'
    storage = upload_fileobj(file.stream, key)
    if not storage:
        import pathlib
        path = pathlib.Path('instance/uploads') / key
        path.parent.mkdir(parents=True, exist_ok=True)
        file.stream.seek(0)
        path.write_bytes(file.stream.read())
        storage = 'local:' + str(path)
    demo = Demo(
        match_id=match_id,
        map_name=map_name,
        part_number=part,
        filename=file.filename,
        storage_key=storage,
        size_bytes=request.content_length,
    )
    db.session.add(demo)
    db.session.commit()
    return jsonify(ok=True, id=demo.id)


@bp.get('/demos/<int:did>/download')
def demo_download(did):
    demo = Demo.query.get_or_404(did)
    if demo.storage_key and demo.storage_key.startswith('local:'):
        from flask import send_file
        return send_file(demo.storage_key[6:], as_attachment=True, download_name=demo.filename)
    url = presigned_download(demo.storage_key)
    if not url:
        abort(404)
    return redirect(url)
