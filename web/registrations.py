"""Inscrição de times: regras, reserva de vaga, cobrança Pix e confirmação."""
from datetime import datetime, timedelta
from web.extensions import db
from web.models import TournamentRegistration, TeamMember, Payment, ROSTER_SIZE, ACTIVE_REG_STATUSES
from web import payments

CHECK_EVERY = timedelta(seconds=8)


def slots_taken(t, exclude_reg_id=None):
    """Vagas ocupadas: confirmados, em análise e quem está com Pix aberto (reserva de 30 min)."""
    regs = TournamentRegistration.query.filter(TournamentRegistration.tournament_id == t.id,
                                               TournamentRegistration.status.in_(ACTIVE_REG_STATUSES)).all()
    taken = 0
    for r in regs:
        if r.id == exclude_reg_id: continue
        if r.status != 'AWAITING_PAYMENT': taken += 1
        else:
            p = r.latest_payment
            if p and p.is_open: taken += 1
    return taken


def slots_left(t, exclude_reg_id=None): return max(0, (t.max_teams or 0) - slots_taken(t, exclude_reg_id))


def problems(t, team, reg=None):
    """O que impede o time de seguir para o pagamento (lista vazia = pode)."""
    out = []
    if not t.is_open: out.append('As inscrições deste campeonato estão fechadas.')
    if len(team.members) != ROSTER_SIZE: out.append(f'O time precisa ter exatamente {ROSTER_SIZE} jogadores (hoje tem {len(team.members)}).')
    pending = [m.user.display_name for m in team.members if not m.user.is_onboarded]
    if pending: out.append('Jogadores sem cadastro completo: ' + ', '.join(pending) + '.')
    ids = [m.user_id for m in team.members] or [0]
    others = (TeamMember.query.join(TournamentRegistration, TournamentRegistration.team_id == TeamMember.team_id)
              .filter(TournamentRegistration.tournament_id == t.id, TournamentRegistration.status.in_(ACTIVE_REG_STATUSES),
                      TeamMember.team_id != team.id, TeamMember.user_id.in_(ids)).all())
    if others: out.append('Já inscritos por outro time: ' + ', '.join(sorted({o.user.display_name for o in others})) + '.')
    if slots_left(t, reg.id if reg else None) <= 0: out.append('Não há vagas disponíveis no momento.')
    return out


def get_or_create(t, team):
    reg = TournamentRegistration.query.filter_by(tournament_id=t.id, team_id=team.id).first()
    if reg and reg.status in ACTIVE_REG_STATUSES: return reg
    if not reg:
        reg = TournamentRegistration(tournament_id=t.id, team_id=team.id); db.session.add(reg)
    reg.created_at = datetime.utcnow(); reg.paid_at = None; reg.admin_note = None
    if (t.entry_fee_cents or 0) <= 0:
        reg.status = 'APPROVED'
    else:
        reg.status = 'AWAITING_PAYMENT'
    db.session.flush()
    return reg


def create_pix(reg, user, payer_email, notification_url=None):
    t, team = reg.tournament, reg.team
    old = reg.latest_payment
    if old and old.is_open: return old
    data = payments.create_pix(t.entry_fee_cents, f'Inscrição {team.name} - {t.name}', payer_email, f'reg-{reg.id}', notification_url)
    p = Payment(registration_id=reg.id, provider='mercadopago', provider_payment_id=data['id'], status=data['status'] or 'pending',
                status_detail=data['status_detail'], amount_cents=t.entry_fee_cents, payer_email=payer_email, qr_code=data['qr_code'],
                qr_code_base64=data['qr_code_base64'], ticket_url=data['ticket_url'], created_by=user.id if user else None,
                expires_at=data['expires_at'] or datetime.utcnow() + timedelta(minutes=payments.PIX_MINUTES), last_checked_at=datetime.utcnow())
    db.session.add(p); db.session.flush()
    return p


def mark_paid(p, when=None, note=None):
    """Pagamento aprovado: confirma a vaga, ou manda para análise se as vagas acabaram enquanto o Pix estava aberto."""
    reg = p.registration
    p.status = 'approved'; p.paid_at = p.paid_at or when or datetime.utcnow()
    if note: p.note = note
    if reg.status in ('APPROVED',): return reg
    reg.paid_at = p.paid_at
    if slots_left(reg.tournament, exclude_reg_id=reg.id) > 0:
        reg.status = 'APPROVED'
    else:
        reg.status = 'PAYMENT_REVIEW'; reg.admin_note = 'Pagamento recebido, mas as vagas já estavam preenchidas. Avaliar reembolso ou abrir vaga.'
    return reg


def apply_provider_status(p, data):
    p.status = data.get('status') or p.status; p.status_detail = data.get('status_detail'); p.last_checked_at = datetime.utcnow()
    if p.status == 'approved': mark_paid(p)
    db.session.flush()
    return p


def sync(p, force=False):
    """Reconsulta o Mercado Pago (no máximo a cada 8s), para funcionar mesmo se o webhook falhar."""
    if p.provider != 'mercadopago' or p.status in ('approved', 'refunded', 'cancelled', 'rejected'): return p
    if not force and p.last_checked_at and datetime.utcnow() - p.last_checked_at < CHECK_EVERY: return p
    try:
        apply_provider_status(p, payments.get_payment(p.provider_payment_id))
    except payments.PaymentError:
        p.last_checked_at = datetime.utcnow()
    return p


def confirm_manual(reg, admin, note=None):
    """Admin confirma pagamento feito por fora (dinheiro no balcão, Pix direto etc.)."""
    p = Payment(registration_id=reg.id, provider='manual', status='pending', amount_cents=reg.tournament.entry_fee_cents or 0,
                created_by=admin.id, note=note or 'Confirmado manualmente pelo admin')
    db.session.add(p); db.session.flush()
    mark_paid(p)
    reg.status = 'APPROVED'
    return reg
