import os
os.environ['DATABASE_URL']='sqlite:///:memory:'
os.environ['SECRET_KEY']='test'
from web.app import create_app

def test_home():
    app=create_app(); app.config['TESTING']=True
    with app.test_client() as c:
        r=c.get('/'); assert r.status_code==200; assert b'CS2' in r.data
