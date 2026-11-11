import json
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from league_auto import install, parse_feed, choose_auto, normalize, prepare, parse_dt


def test_three_feed_types():
    j='{"fixtures":[{"date":"2026-11-09","time":"22:40","home":"Los Intocables","away":"Gran Rival"}]}'
    c='fecha,hora,local,visitante\n09/11/2026,22:40,Los Intocables,Gran Rival\n'
    i='BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;TZID=Europe/Madrid:20261109T224000\nSUMMARY:Los Intocables vs Gran Rival\nEND:VEVENT\nEND:VCALENDAR'
    for f,t in [('json',j),('csv',c),('ics',i)]:
        rows=parse_feed(t,f,'afj-cuarta','Los Intocables')
        assert len(rows)==1
        assert rows[0]['opponent']=='Gran Rival'
        assert rows[0]['starts_at'].startswith('2026-11-09T21:40')


def test_do_not_guess_competitions():
    games=[{'id':'1','opponent':'Real Rival','when':parse_dt('2026-11-09T22:55:00+01:00')}]
    fixtures=[{'uid':'a','opponent':'Real Rival','starts_at':'2026-11-09T21:40:00Z','competition_slug':'afj-cuarta'},
              {'uid':'b','opponent':'Real Rival','starts_at':'2026-11-09T21:40:00Z','competition_slug':'vpg-quinta'}]
    matched,ambiguous=choose_auto(games,fixtures)
    assert not matched and ambiguous==['1']
    assert normalize('Atlético-FC')==normalize('Atletico FC')


def test_classify_persists_and_respects_manual(tmp_path):
    path=tmp_path/'stats.db'
    @contextmanager
    def db():
        conn=sqlite3.connect(path)
        conn.execute('CREATE TABLE IF NOT EXISTS match_archive (match_id TEXT PRIMARY KEY,payload TEXT,saved_at TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS match_labels (match_id TEXT PRIMARY KEY,competition_slug TEXT,label TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS fixtures (id INTEGER PRIMARY KEY,competition_slug TEXT,opponent TEXT, starts_at TEXT,status TEXT)')
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    with db() as conn:
        conn.execute('INSERT INTO fixtures VALUES (1,?,?,?,?)',('afj-cuarta','Los Cracks','2026-11-09T22:40:00','programado'))
        conn.execute('INSERT INTO match_labels VALUES (?,?,?)',('manual','vpg-quinta','Otra clasificación confirmada'))
    state={'matches':[{'matchId':'real','opponentName':'Los Cracks','timestamp':'2026-11-09T21:55:00+00:00'},
                      {'matchId':'manual','opponentName':'Los Cracks','timestamp':'2026-11-09T21:58:00+00:00'}]}
    app=FastAPI()
    installed=install(app,db_provider=db,state_getter=lambda:state,is_admin=lambda r:False)
    assert installed['classify']()==1
    with TestClient(app) as client:
        status=client.get('/api/ligas/estado')
        assert status.status_code==200
        assert status.json()['autoclasificados_total']==1
        result=client.get('/api/ligas/partidos').json()['matches']
        assert result['real']['label']=='AFJ División 4A'
        with db() as conn:
            assert conn.execute('SELECT label FROM match_labels WHERE match_id="manual"').fetchone()[0]=='Otra clasificación confirmada'
        assert client.post('/api/admin/ligas/recalcular').status_code==403


def test_three_leagues_are_correct_and_distinct():
    from league_auto import DEFAULT_SLUGS, competitions_catalog
    assert len(DEFAULT_SLUGS)==3
    assert DEFAULT_SLUGS['vpg-quinta']=='VPG División 5C'
    assert DEFAULT_SLUGS['afj-cuarta']=='AFJ División 4A'
    assert DEFAULT_SLUGS['vpg-bronze-zero']=='VPG Zero Bronze'
    labels=competitions_catalog()
    assert len(labels)==3 and all(not x['calendario_conectado'] for x in labels)
    assert all(x['partidos_clasificados']==0 for x in labels)
