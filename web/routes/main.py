from flask import Blueprint, render_template
from web.models import Tournament, Match
bp=Blueprint('main',__name__)
@bp.get('/')
def home(): return render_template('home.html', tournaments=Tournament.query.order_by(Tournament.id.desc()).all(), matches=Match.query.order_by(Match.id.desc()).limit(12).all())
