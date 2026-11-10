"""Pruebas rápidas del HUB sin consultar a EA ni iniciar Discord."""
import base64
import importlib
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def test_hub_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_SOURCE', 'bot')
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'hub.sqlite3'))
    monkeypatch.setenv('ADMIN_USER', 'editor')
    monkeypatch.setenv('ADMIN_PASSWORD', 'very-long-unique-test-password')
    monkeypatch.setenv('SESSION_SECRET', 'random-session-secret-for-hub-test')
    monkeypatch.setenv('HUB_SYNC_TOKEN', 'hub-secret-for-testing-1234567890')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import main
    importlib.reload(main)
    with TestClient(main.app) as client:
        assert client.get('/').status_code == 200
        assert client.get('/competiciones').status_code == 200
        assert client.get('/fichajes').status_code == 200
        assert client.get('/api/hub').status_code == 200
        hub = client.get('/api/hub').json()
        assert len(hub['competitions']) == 3
        assert hub['fixtures'] == []
        assert client.get('/admin', follow_redirects=False).status_code == 303
        assert client.post('/api/admin/fixture', json={'opponent':'Rival','starts_at':'2026-11-06T22:00'}).status_code == 403
        assert client.post('/api/integrations/bot/snapshot',json={'members': [],'matches':[]}).status_code == 401
        assert client.post('/api/login',json={'username':'editor','password':'bad'}).status_code == 401
        assert client.post('/api/login',json={'username':'editor','password':'very-long-unique-test-password'}).status_code == 200
        assert client.get('/admin').status_code == 200
        upload=client.post('/api/admin/player/photo',json={'player_key':'Jugador A','filename':'test.png','image_base64':base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'fake-image-bytes').decode()})
        assert upload.status_code==200,upload.text
        assert client.get('/api/player-photo/Jugador%20A').headers['content-type'].startswith('image/png')
        fixture={'competition_slug':'afj-cuarta','opponent':'Rival de prueba','starts_at':'2026-11-07T22:40','venue':'Casa','status':'programado','notes':'Jornada 1'}
        create=client.post('/api/admin/fixture',json=fixture)
        assert create.status_code==200, create.text
        fixture_id=create.json()['id']
        assert client.get('/api/hub').json()['fixtures'][0]['opponent']=='Rival de prueba'
        assert client.put('/api/admin/fixture/'+str(fixture_id),json={**fixture,'opponent':'Rival 2'}).status_code==200
        assert client.put('/api/admin/competition/afj-cuarta',json={'name':'AFJ - 4ª División','timetable':'22:40'}).status_code==200
        assert client.put('/api/admin/match/123/label',json={'label':'Amistoso'}).status_code==200
        assert client.get('/api/hub').json()['match_labels']['123']['label']=='Amistoso'
        assert client.delete('/api/admin/fixture/'+str(fixture_id)).status_code==200
        payload={'club_id':5360,'club':{'clubName':'Los Intocables'},'overall':{'wins':4},'members':[{'playerName':'Jugador A','goals':2}],
                 'matches':[{'matchId':'123','opponentName':'Rival','goals':2,'goalsAgainst':1}], 'updated_at':'2026-11-06T16:00:00+00:00'}
        r=client.post('/api/integrations/bot/snapshot',json=payload,headers={'Authorization':'Bearer hub-secret-for-testing-1234567890'})
        assert r.status_code==200, r.text
        assert client.get('/api/club').json()['source']=='discord-bot'
        assert client.get('/api/partidos/123').json()['match']['goals']==2
        assert len(client.get('/api/partidos').json()['matches'])==1
        assert client.post('/api/logout').status_code==200
        assert client.get('/api/admin/applications').status_code==403
        app=client.post('/api/fichajes/solicitud',json={'alias':'Jugador Nuevo','platform':'PC','position':'DC','notes':'Pruebas'})
        assert app.status_code==201,app.text
        client.post('/api/login',json={'username':'editor','password':'very-long-unique-test-password'})
        items=client.get('/api/admin/applications').json()['applications']
        assert len(items)==1
        assert client.patch('/api/admin/applications/'+str(items[0]['id']),json={'status':'en_pruebas'}).status_code==200
        assert client.get('/api/admin/applications').json()['applications'][0]['status']=='en_pruebas'
