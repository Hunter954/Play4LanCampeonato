import socket
import struct
import random

SERVERDATA_RESPONSE_VALUE = 0
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_AUTH = 3


class RCONError(RuntimeError):
    pass


def _pack_packet(request_id: int, packet_type: int, body: str) -> bytes:
    payload = struct.pack('<ii', request_id, packet_type) + body.encode('utf-8') + b'\x00\x00'
    return struct.pack('<i', len(payload)) + payload


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise RCONError('Conexão RCON encerrada pelo servidor.')
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def _recv_packet(sock: socket.socket):
    raw_size = _recv_exact(sock, 4)
    (size,) = struct.unpack('<i', raw_size)
    if size < 10 or size > 10_000_000:
        raise RCONError(f'Pacote RCON inválido: {size} bytes.')
    payload = _recv_exact(sock, size)
    request_id, packet_type = struct.unpack('<ii', payload[:8])
    body = payload[8:-2].decode('utf-8', errors='replace')
    return request_id, packet_type, body


class RCONClient:
    """Cliente mínimo do protocolo Source RCON usado pelo CS2.

    Abre uma conexão por comando. Isso é proposital para o Agent: simples,
    isolado e tolerante a reinícios do servidor.
    """

    def __init__(self, host='127.0.0.1', port=27015, password='', timeout=2.5):
        self.host = host
        self.port = int(port)
        self.password = password or ''
        self.timeout = float(timeout)

    def command(self, command: str) -> str:
        if not self.password:
            raise RCONError('rcon_password não configurado no Agent.')
        request_id = random.randint(1, 2_000_000_000)
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.settimeout(self.timeout)
            sock.sendall(_pack_packet(request_id, SERVERDATA_AUTH, self.password))

            authenticated = False
            for _ in range(3):
                rid, ptype, _ = _recv_packet(sock)
                if ptype == SERVERDATA_AUTH_RESPONSE:
                    if rid == -1:
                        raise RCONError('Senha RCON incorreta.')
                    if rid == request_id:
                        authenticated = True
                        break
            if not authenticated:
                raise RCONError('Servidor não confirmou autenticação RCON.')

            command_id = request_id + 1
            sock.sendall(_pack_packet(command_id, SERVERDATA_EXECCOMMAND, command))

            parts = []
            while True:
                try:
                    rid, _ptype, body = _recv_packet(sock)
                except socket.timeout:
                    break
                if rid != command_id:
                    continue
                parts.append(body)
                # A maioria dos comandos do CS2 cabe em um pacote. Continuamos
                # até timeout curto para também capturar respostas maiores.
                sock.settimeout(0.15)
            return ''.join(parts).strip()
