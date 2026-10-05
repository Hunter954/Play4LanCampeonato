from datetime import datetime
from flask_login import UserMixin
from web.extensions import db

def now(): return datetime.utcnow()

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

ROSTER_SIZE = 5

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

    @property
    def maps(self): return [m.strip() for m in (self.map_pool or '').split(',') if m.strip()]
    @property
    def approved_count(self): return TournamentRegistration.query.filter_by(tournament_id=self.id, status='APPROVED').count()
    @property
    def registration_count(self): return TournamentRegistration.query.filter(TournamentRegistration.tournament_id==self.id, TournamentRegistration.status!='REJECTED').count()
    @property
    def is_open(self): return self.status == 'REGISTRATION'

class TournamentRegistration(db.Model):
    id=db.Column(db.Integer, primary_key=True); tournament_id=db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    team_id=db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False); status=db.Column(db.String(20), default='PENDING'); created_at=db.Column(db.DateTime, default=now)
    tournament=db.relationship('Tournament'); team=db.relationship('Team'); __table_args__=(db.UniqueConstraint('tournament_id','team_id'),)

class Match(db.Model):
    id=db.Column(db.Integer, primary_key=True); tournament_id=db.Column(db.Integer, db.ForeignKey('tournament.id'))
    team1_id=db.Column(db.Integer, db.ForeignKey('team.id')); team2_id=db.Column(db.Integer, db.ForeignKey('team.id'))
    status=db.Column(db.String(30), default='SCHEDULED'); server_id=db.Column(db.String(50)); best_of=db.Column(db.Integer, default=1)
    team1_score=db.Column(db.Integer, default=0); team2_score=db.Column(db.Integer, default=0); current_map=db.Column(db.String(80)); round_number=db.Column(db.Integer, default=0)
    created_at=db.Column(db.DateTime, default=now); team1=db.relationship('Team', foreign_keys=[team1_id]); team2=db.relationship('Team', foreign_keys=[team2_id])

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
