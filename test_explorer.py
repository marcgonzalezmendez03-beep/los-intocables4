import json
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from match_explorer import install, raw_overview

RAW = {'matchId':'4567','timestamp':1762500000,
       'clubs':{
           '5360':{'goals':'3','goalsAgainst':'1','details':{'name':'Los Intocables'}},
           '777':{'goals':'1','goalsAgainst':'3','details':{'name':'Equipo Rival'}}},
       'players':{
           '5360':{'p1':{'playername':'Eric','pos':'forward','rating':'9.2','goals':'2','assists':'1','shots':'4','passesmade':'15','passattempts':'20'},
                   'p2':{'playername':'Elliot','pos':'midfielder','rating':'7.8','goals':'1','assists':'1','shots':'2','passesmade':'30','passattempts':'35'}},
           '777':{'p3':{'playername':'Visitante','pos':'forward','rating':'6.5','goals':'1','assists':'0','shots':'5'}}},
       'aggregate':{'5360':{'shots':'12','passattempts':'140','passesmade':'113','tacklesmade':'8'},
                    '777':{'shots':'8','passattempts':'120','passesmade':'90','tacklesmade':'5'}}}

class FakeEA:
    def __init__(self):
        self.calls=[]
    def get_club_matches(self, cid, match_type, count, output):
        assert str(cid)=='5360' and count==10 and output=='raw'
        self.calls.append(match_type)
        return [RAW] if match_type=='leagueMatch' else []


def test_raw_parsing():
    m=raw_overview(RAW,'5360','leagueMatch')
    assert m['goals']==3 and m['goalsAgainst']==1 and m['result']=='win'
    assert m['hasPlayers'] is True
    assert len(m['teams'])==2
    assert m['teams'][0]['players'][0]['name']=='Eric'
    assert m['teams'][0]['players'][0]['stats']['passesCompleted']==15
    assert m['teams'][1]['players'][0]['stats']['goals']==1
    assert m['teams'][0]['metrics']['shots']==12


def test_endpoints_archive_and_fallback(tmp_path):
    database=tmp_path/'db.sqlite3'
    @contextmanager
    def db():
        conn=sqlite3.connect(database)
        conn.execute('CREATE TABLE IF NOT EXISTS match_archive (match_id TEXT PRIMARY KEY, payload TEXT NOT NULL, saved_at TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS match_labels (match_id TEXT PRIMARY KEY,label TEXT, competition_slug TEXT)')
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    with db() as conn:
        conn.execute('INSERT INTO match_archive VALUES (?,?,?)', ('ancient', json.dumps({'matchId':'ancient','goals':1,'goalsAgainst':0,'opponentName':'Antiguo','timestamp':1720000000}), '2026-01-01T00:00:00Z'))
        conn.execute('INSERT INTO match_labels VALUES (?,?,?)',('4567','AFJ cuarta división','afj-cuarta'))
    state={'club_id':5360,'matches':[{'matchId':'4567','opponentName':'Equipo Rival','goals':3,'goalsAgainst':1,'timestamp':1762500000}]}
    fake=FakeEA()
    app=FastAPI()
    installer=install(app, state_getter=lambda:state, db_provider=db, api=fake, club_name='Los Intocables')
    installer['sync_raw']()
    with TestClient(app) as client:
        current=client.get('/api/explorador/partidos/4567')
        assert current.status_code==200
        data=current.json()
        assert data['source']=='ea_raw'
        assert data['label']['label']=='AFJ cuarta división'
        assert len(data['teams'][0]['players'])==2
        assert data['teams'][0]['players'][0]['stats']['goals']==2
        old=client.get('/api/explorador/partidos/ancient')
        assert old.status_code==200
        assert old.json()['source']=='resumen'
        assert old.json()['hasPlayers'] is False
        listing=client.get('/api/explorador/partidos?limit=10').json()
        assert listing['total']==2
        assert listing['matches'][0]['matchId']=='4567'
        health=client.get('/api/explorador/estado').json()
        assert health['partidos_detallados_guardados']==1
        assert client.get('/api/explorador/partidos/bad-id').status_code==404
