from datetime import datetime
from flask_login import UserMixin
from web.extensions import db

def now(): return datetime.utcnow()

ROSTER_SIZE = 5
# Inscrições que ocupam (ou podem ocupar) vaga e travam o elenco.
ACTIVE_REG_STATUSES = ('AWAITING_PAYMENT', 'PAYMENT_REVIEW', 'PENDING', 'APPROVED')

class User(UserMixin, db.Model):
    id=db.Column(db.Integer, primary_key=True)
    email=db.Column(db.String(255), unique=True, nullable=True)
    password_hash=db.Column(db.String(255), nullable=True)
    steam_id64=db.Column(db.String(32), unique=True, nullable=True, index=True)
    steam_name=db.Column(db.String(255)); steam_avatar=db.Column(db.String(500)); steam_profile_url=db.Column(db.String(500))
    real_name=db.Column(db.String(255)); nickname=db.Column(db.String(80)); avatar_url=db.Column(db.String(500))
    is_admin=db.Column(db.Boolean, default=False); created_at=db.Column(db.DateTime, default=now)
    whatsapp=db.Column(db.String(32)); city=db.Column(db.String(80)); bio=db.Column(db.String(280))
    onboarded_at=db.Column(db.DateTime); last_login_at=db.Column(db.DateTime)

    @property
    def display_name(self): return self.nickname or self.steam_name or (f'Jogador {self.steam_id64[-4:]}' if self.steam_id64 else 'Jogador')
    @property
    def avatar(self): return self.avatar_url or self.steam_avatar
    @property
    def is_onboarded(self): return bool(self.onboarded_at and self.nickname and self.real_name)
    @property
    def memberships(self): return TeamMember.query.filter_by(user_id=self.id).order_by(TeamMember.joined_at).all()

class Team(db.Model):
    id=db.Column(db.Integer, primary_key=True); name=db.Column(db.String(120), nullable=False); tag=db.Column(db.String(24), nullable=False)
    logo_url=db.Column(db.String(500)); owner_id=db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False); created_at=db.Column(db.DateTime, default=now)
    description=db.Column(db.String(280))
    owner=db.relationship('User', foreign_keys=[owner_id])
    members=db.relationship('TeamMember', cascade='all, delete-orphan', backref='team')

    @property
    def is_full(self): return len(self.members) >= ROSTER_SIZE
    @property
    def roster(self): return sorted(self.members, key=lambda m: (m.user_id != self.owner_id, m.joined_at or now()))
    def has_member(self, user): return bool(user and getattr(user, 'id', None) and any(m.user_id == user.id for m in self.members))
    @property
    def locking_registration(self):
        """Inscrição ativa em campeonato não finalizado: enquanto existir, o elenco fica travado."""
        return (TournamentRegistration.query.join(Tournament)
                .filter(TournamentRegistration.team_id==self.id, TournamentRegistration.status.in_(ACTIVE_REG_STATUSES), Tournament.status!='FINISHED')
                .first())

class TeamMember(db.Model):
    id=db.Column(db.Integer, primary_key=True); team_id=db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    user_id=db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False); role=db.Column(db.String(20), default='PLAYER'); joined_at=db.Column(db.DateTime, default=now)
    user=db.relationship('User'); __table_args__=(db.UniqueConstraint('team_id','user_id'),)

class Invite(db.Model):
    id=db.Column(db.Integer, primary_key=True); token=db.Column(db.String(80), unique=True, nullable=False, index=True)
    team_id=db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False); created_by=db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    active=db.Column(db.Boolean, default=True); created_at=db.Column(db.DateTime, default=now)
    team=db.relationship('Team')

class Tournament(db.Model):
    id=db.Column(db.Integer, primary_key=True); name=db.Column(db.String(160), nullable=False); description=db.Column(db.Text)
    status=db.Column(db.String(30), default='REGISTRATION'); max_teams=db.Column(db.Integer, default=16); format=db.Column(db.String(30), default='DOUBLE_ELIMINATION')
    map_pool=db.Column(db.Text, default='Mirage,Inferno,Nuke,Ancient,Anubis,Dust II,Train'); created_at=db.Column(db.DateTime, default=now)
    starts_at=db.Column(db.DateTime); location=db.Column(db.String(160)); prize=db.Column(db.Text); rules=db.Column(db.Text)
    entry_fee_cents=db.Column(db.Integer, default=0)
    bo_default=db.Column(db.Integer, default=1); bo_upper_final=db.Column(db.Integer, default=3)
    bo_lower_final=db.Column(db.Integer, default=1); bo_grand_final=db.Column(db.Integer, default=3)

    @property
    def maps(self): return [m.strip() for m in (self.map_pool or '').split(',') if m.strip()]
    @property
    def approved_count(self): return TournamentRegistration.query.filter_by(tournament_id=self.id, status='APPROVED').count()
    @property
    def registration_count(self): return TournamentRegistration.query.filter(TournamentRegistration.tournament_id==self.id, TournamentRegistration.status.in_(ACTIVE_REG_STATUSES)).count()
    @property
    def is_open(self): return self.status == 'REGISTRATION'
    @property
    def has_bracket(self): return Match.query.filter_by(tournament_id=self.id).filter(Match.bracket.isnot(None)).first() is not None
    @property
    def entry_fee(self): return (self.entry_fee_cents or 0) / 100
    @property
    def grand_final(self): return Match.query.filter_by(tournament_id=self.id, bracket='FINAL').first()
    @property
    def champion(self):
        gf = self.grand_final
        return gf.winner if gf and gf.status == 'FINISHED' else None

class TournamentRegistration(db.Model):
    id=db.Column(db.Integer, primary_key=True); tournament_id=db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    team_id=db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False); status=db.Column(db.String(20), default='PENDING'); created_at=db.Column(db.DateTime, default=now)
    seed=db.Column(db.Integer); paid_at=db.Column(db.DateTime); admin_note=db.Column(db.String(280))
    tournament=db.relationship('Tournament'); team=db.relationship('Team'); __table_args__=(db.UniqueConstraint('tournament_id','team_id'),)

    @property
    def latest_payment(self): return Payment.query.filter_by(registration_id=self.id).order_by(Payment.id.desc()).first()

class Payment(db.Model):
    id=db.Column(db.Integer, primary_key=True)
    registration_id=db.Column(db.Integer, db.ForeignKey('tournament_registration.id'), nullable=False, index=True)
    provider=db.Column(db.String(20), default='mercadopago'); provider_payment_id=db.Column(db.String(64), index=True)
    status=db.Column(db.String(20), default='pending'); status_detail=db.Column(db.String(80))
    amount_cents=db.Column(db.Integer, nullable=False); payer_email=db.Column(db.String(255))
    qr_code=db.Column(db.Text); qr_code_base64=db.Column(db.Text); ticket_url=db.Column(db.String(500))
    expires_at=db.Column(db.DateTime); paid_at=db.Column(db.DateTime); last_checked_at=db.Column(db.DateTime)
    created_by=db.Column(db.Integer, db.ForeignKey('user.id')); created_at=db.Column(db.DateTime, default=now)
    note=db.Column(db.String(280))
    registration=db.relationship('TournamentRegistration')

    @property
    def is_open(self): return self.status in ('pending', 'in_process') and (not self.expires_at or self.expires_at > now())

class Match(db.Model):
    id=db.Column(db.Integer, primary_key=True); tournament_id=db.Column(db.Integer, db.ForeignKey('tournament.id'))
    team1_id=db.Column(db.Integer, db.ForeignKey('team.id')); team2_id=db.Column(db.Integer, db.ForeignKey('team.id'))
    status=db.Column(db.String(30), default='SCHEDULED'); server_id=db.Column(db.String(50)); best_of=db.Column(db.Integer, default=1)
    team1_score=db.Column(db.Integer, default=0); team2_score=db.Column(db.Integer, default=0); current_map=db.Column(db.String(80)); round_number=db.Column(db.Integer, default=0)
    created_at=db.Column(db.DateTime, default=now); team1=db.relationship('Team', foreign_keys=[team1_id]); team2=db.relationship('Team', foreign_keys=[team2_id])
    # Chaveamento
    bracket=db.Column(db.String(10)); round=db.Column(db.Integer); position=db.Column(db.Integer); label=db.Column(db.String(60))
    team1_from=db.Column(db.String(20)); team2_from=db.Column(db.String(20))
    next_match_id=db.Column(db.Integer); next_slot=db.Column(db.Integer); loser_match_id=db.Column(db.Integer); loser_slot=db.Column(db.Integer)
    winner_id=db.Column(db.Integer, db.ForeignKey('team.id')); walkover=db.Column(db.Boolean, default=False)
    config_token=db.Column(db.String(64)); started_at=db.Column(db.DateTime); finished_at=db.Column(db.DateTime)
    winner=db.relationship('Team', foreign_keys=[winner_id])
    tournament=db.relationship('Tournament')

    @property
    def maps_played(self): return MatchMap.query.filter_by(match_id=self.id).order_by(MatchMap.map_number).all()
    @property
    def loser_id(self):
        if not self.winner_id: return None
        return self.team2_id if self.winner_id == self.team1_id else self.team1_id
    def team_for_slot(self, slot): return self.team1 if slot == 1 else self.team2
    def slot_of(self, team_id): return 1 if team_id and team_id == self.team1_id else 2 if team_id and team_id == self.team2_id else None

class MatchMap(db.Model):
    id=db.Column(db.Integer, primary_key=True); match_id=db.Column(db.Integer, db.ForeignKey('match.id'), nullable=False, index=True)
    map_number=db.Column(db.Integer, nullable=False); map_name=db.Column(db.String(40), nullable=False)
    picked_by_id=db.Column(db.Integer, db.ForeignKey('team.id')); status=db.Column(db.String(20), default='PENDING')
    team1_score=db.Column(db.Integer, default=0); team2_score=db.Column(db.Integer, default=0); winner_id=db.Column(db.Integer, db.ForeignKey('team.id'))
    picked_by=db.relationship('Team', foreign_keys=[picked_by_id])
    __table_args__=(db.UniqueConstraint('match_id','map_number'),)

class VetoAction(db.Model):
    id=db.Column(db.Integer, primary_key=True); match_id=db.Column(db.Integer, db.ForeignKey('match.id'), nullable=False, index=True)
    step=db.Column(db.Integer, nullable=False); team_id=db.Column(db.Integer, db.ForeignKey('team.id')); action=db.Column(db.String(10), nullable=False)
    map_name=db.Column(db.String(40), nullable=False); user_id=db.Column(db.Integer, db.ForeignKey('user.id')); created_at=db.Column(db.DateTime, default=now)
    team=db.relationship('Team'); user=db.relationship('User')
    __table_args__=(db.UniqueConstraint('match_id','step'),)

STAT_FIELDS = ('kills','deaths','assists','damage','headshot_kills','rounds_played','kast','mvp','score','utility_damage','enemies_flashed',
               'flash_assists','first_kills','first_deaths','trade_kills','clutches_won','bomb_plants','bomb_defuses','k1','k2','k3','k4','k5')

class PlayerMapStat(db.Model):
    id=db.Column(db.Integer, primary_key=True); match_id=db.Column(db.Integer, db.ForeignKey('match.id'), nullable=False, index=True)
    map_number=db.Column(db.Integer, nullable=False, default=1); steam_id64=db.Column(db.String(32), nullable=False, index=True)
    user_id=db.Column(db.Integer, db.ForeignKey('user.id'), index=True); team_id=db.Column(db.Integer, db.ForeignKey('team.id'))
    name=db.Column(db.String(120)); source=db.Column(db.String(20), default='matchzy'); updated_at=db.Column(db.DateTime, default=now, onupdate=now)
    kills=db.Column(db.Integer, default=0); deaths=db.Column(db.Integer, default=0); assists=db.Column(db.Integer, default=0); damage=db.Column(db.Integer, default=0)
    headshot_kills=db.Column(db.Integer, default=0); rounds_played=db.Column(db.Integer, default=0); kast=db.Column(db.Integer, default=0)
    mvp=db.Column(db.Integer, default=0); score=db.Column(db.Integer, default=0); utility_damage=db.Column(db.Integer, default=0)
    enemies_flashed=db.Column(db.Integer, default=0); flash_assists=db.Column(db.Integer, default=0); first_kills=db.Column(db.Integer, default=0)
    first_deaths=db.Column(db.Integer, default=0); trade_kills=db.Column(db.Integer, default=0); clutches_won=db.Column(db.Integer, default=0)
    bomb_plants=db.Column(db.Integer, default=0); bomb_defuses=db.Column(db.Integer, default=0)
    k1=db.Column(db.Integer, default=0); k2=db.Column(db.Integer, default=0); k3=db.Column(db.Integer, default=0); k4=db.Column(db.Integer, default=0); k5=db.Column(db.Integer, default=0)
    user=db.relationship('User'); team=db.relationship('Team')
    __table_args__=(db.UniqueConstraint('match_id','map_number','steam_id64'),)

class MatchEvent(db.Model):
    id=db.Column(db.Integer, primary_key=True); event_uuid=db.Column(db.String(80), unique=True, nullable=False); server_id=db.Column(db.String(50)); match_id=db.Column(db.Integer, db.ForeignKey('match.id'))
    event_type=db.Column(db.String(80), nullable=False); payload=db.Column(db.JSON, default=dict); created_at=db.Column(db.DateTime, default=now)

class Server(db.Model):
    id=db.Column(db.Integer, primary_key=True); code=db.Column(db.String(50), unique=True, nullable=False); display_name=db.Column(db.String(100)); host_id=db.Column(db.String(100))
    status=db.Column(db.String(30), default='OFFLINE'); current_match_id=db.Column(db.Integer, db.ForeignKey('match.id')); last_heartbeat=db.Column(db.DateTime)

class ServerCommand(db.Model):
    id=db.Column(db.Integer, primary_key=True); host_id=db.Column(db.String(100), nullable=False); server_code=db.Column(db.String(50)); command=db.Column(db.String(80), nullable=False)
    payload=db.Column(db.JSON, default=dict); status=db.Column(db.String(20), default='PENDING'); created_at=db.Column(db.DateTime, default=now); completed_at=db.Column(db.DateTime)

class Demo(db.Model):
    id=db.Column(db.Integer, primary_key=True); match_id=db.Column(db.Integer, db.ForeignKey('match.id')); map_name=db.Column(db.String(80)); part_number=db.Column(db.Integer, default=1)
    filename=db.Column(db.String(255), nullable=False); storage_key=db.Column(db.String(800)); size_bytes=db.Column(db.BigInteger); created_at=db.Column(db.DateTime, default=now)

class Incident(db.Model):
    id=db.Column(db.Integer, primary_key=True); match_id=db.Column(db.Integer, db.ForeignKey('match.id')); description=db.Column(db.Text, nullable=False); created_at=db.Column(db.DateTime, default=now)


class AdminSetting(db.Model):
    id=db.Column(db.Integer, primary_key=True)
    key=db.Column(db.String(100), unique=True, nullable=False, index=True)
    value=db.Column(db.Text, nullable=False)
    updated_at=db.Column(db.DateTime, default=now, onupdate=now)
