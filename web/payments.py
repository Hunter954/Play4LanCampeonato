"""Pix via Mercado Pago (API de pagamentos v1).

Variáveis de ambiente:
- MP_ACCESS_TOKEN: Access Token de produção da aplicação Mercado Pago (obrigatório para cobrar).
- MP_WEBHOOK_SECRET: assinatura secreta do webhook (opcional, mas recomendado).
"""
import hashlib, hmac, os, uuid
from datetime import datetime, timedelta, timezone
import requests

API = 'https://api.mercadopago.com'
PIX_MINUTES = 30


class PaymentError(Exception):
    pass


def enabled(): return bool(os.getenv('MP_ACCESS_TOKEN'))


def _headers(extra=None):
    h = {'Authorization': f"Bearer {os.getenv('MP_ACCESS_TOKEN', '')}", 'Content-Type': 'application/json'}
    h.update(extra or {}); return h


def _parse(data):
    tx = ((data.get('point_of_interaction') or {}).get('transaction_data') or {})
    exp = data.get('date_of_expiration')
    expires = None
    if exp:
        try: expires = datetime.fromisoformat(exp.replace('Z', '+00:00')).astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError: expires = None
    return {'id': str(data.get('id')), 'status': data.get('status'), 'status_detail': data.get('status_detail'),
            'qr_code': tx.get('qr_code'), 'qr_code_base64': tx.get('qr_code_base64'), 'ticket_url': tx.get('ticket_url'),
            'expires_at': expires, 'external_reference': data.get('external_reference'),
            'amount': data.get('transaction_amount')}


def create_pix(amount_cents, description, payer_email, external_reference, notification_url=None):
    if not enabled(): raise PaymentError('Pagamento online ainda não configurado. Fale com a organização.')
    expires = datetime.now(timezone.utc) + timedelta(minutes=PIX_MINUTES)
    body = {'transaction_amount': round(amount_cents / 100, 2), 'description': description[:250], 'payment_method_id': 'pix',
            'payer': {'email': payer_email}, 'external_reference': external_reference,
            'date_of_expiration': expires.isoformat(timespec='milliseconds')}
    if notification_url and notification_url.startswith('https://'): body['notification_url'] = notification_url
    try:
        r = requests.post(f'{API}/v1/payments', json=body, headers=_headers({'X-Idempotency-Key': str(uuid.uuid4())}), timeout=20)
    except requests.RequestException as e:
        raise PaymentError('Não foi possível falar com o Mercado Pago. Tente de novo em instantes.') from e
    data = r.json() if r.content else {}
    if r.status_code >= 400:
        raise PaymentError(f"Mercado Pago recusou a cobrança: {data.get('message') or r.status_code}")
    return _parse(data)


def get_payment(payment_id):
    try:
        r = requests.get(f'{API}/v1/payments/{payment_id}', headers=_headers(), timeout=15)
    except requests.RequestException as e:
        raise PaymentError('Mercado Pago indisponível.') from e
    if r.status_code >= 400: raise PaymentError(f'Consulta do pagamento falhou ({r.status_code}).')
    return _parse(r.json())


def valid_signature(signature_header, request_id, data_id):
    """Valida o cabeçalho x-signature do webhook. Sem MP_WEBHOOK_SECRET configurado, aceita (o status é sempre reconsultado na API)."""
    secret = os.getenv('MP_WEBHOOK_SECRET')
    if not secret: return True
    parts = dict(p.strip().split('=', 1) for p in (signature_header or '').split(',') if '=' in p)
    ts, v1 = parts.get('ts'), parts.get('v1')
    if not ts or not v1: return False
    manifest = (f'id:{str(data_id).lower()};' if data_id else '') + (f'request-id:{request_id};' if request_id else '') + f'ts:{ts};'
    expected = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)
