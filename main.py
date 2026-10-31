import asyncio, json, logging, os, secrets, sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware
from fc_clubs_api import FC27API

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
CLUB_NAME = os.getenv('CLUB_NAME', 'Los Intocables')
REFRESH_MINUTES = max(5, int(os.getenv('REFRESH_MINUTES', '5')))
ADMIN_USER = os.getenv('ADMIN_USER', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')
SESSION_SECRET = os.getenv('SESSION_SECRET', '')
DB_PATH = ROOT / 'site.db'
logger = logging.getLogger('intocables')
logging.basicConfig(level=logging.INFO)
api = FC27API(timezone='Europe/Madrid')
state = {'club_id': None, 'club': None, 'overall': None, 'members': [], 'matches': [], 'updated_at': None, 'error': None}
lock = Lock()

def normalized(obj):
    if hasattr(obj, 'to_dict'):
        return normalized(obj.to_dict(orient='records'))
    if isinstance(obj, (tuple, list)):
        return [normalized(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): normalized(v) for k, v in obj.items()}
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    return obj

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS match_archive (match_id TEXT PRIMARY KEY, payload TEXT NOT NULL, saved_at TEXT NOT NULL)')
    return conn

def get_settings():
    with db() as conn:
        return {k: json.loads(v) for k, v in conn.execute('SELECT key,value FROM settings')}

def fetch():
    club_id = api.find_club_id(CLUB_NAME)
    return normalized({'club_id': club_id, 'club': api.get_club_details(club_id),
      'overall': api.get_club_overall_stats(club_id), 'members': api.get_member_stats(club_id),
      'matches': api.get_club_matches(club_id, count=30),
      'updated_at': datetime.now(timezone.utc).isoformat(), 'error': None})

async def refresh():
    try:
        data = await asyncio.to_thread(fetch)
        with lock:
            state.update(json.loads(json.dumps(data, default=str)))
        with db() as conn:
            for match in data.get('matches', []):
                if not isinstance(match, dict): continue
                mid = match.get('matchId') or match.get('match_id')
                if mid is None: continue
                conn.execute('INSERT OR REPLACE INTO match_archive(match_id,payload,saved_at) VALUES (?,?,?)', (str(mid), json.dumps(match, ensure_ascii=False, default=str), datetime.now(timezone.utc).isoformat()))
        logger.info('FC27 actualizado: %s', CLUB_NAME)
    except Exception as exc:
        logger.exception('Fallo al consultar FC27')
        with lock:
            state['error'] = f'{type(exc).__name__}: {exc}'

async def poll():
    while True:
        await asyncio.sleep(REFRESH_MINUTES * 60)
        await refresh()

@asynccontextmanager
async def lifespan(app):
    with db(): pass
    task = asyncio.create_task(poll())
    await refresh()
    yield
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass

app = FastAPI(title='Los Intocables · FC27', lifespan=lifespan)
# Configure SESSION_SECRET in .env before exposing the site to the internet.
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET or secrets.token_urlsafe(48), same_site='lax', https_only=os.getenv('COOKIE_SECURE','false').lower()=='true')
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
templates = Jinja2Templates(directory=ROOT / 'templates')

def is_admin(request):
    return request.session.get('admin') is True

@app.get('/', response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, 'index.html', {'club_name': CLUB_NAME, 'admin': is_admin(request)})

@app.get('/api/club')
async def club_data():
    with lock: snapshot = json.loads(json.dumps(state))
    return {**snapshot, 'customization': get_settings(), 'player_profiles': get_player_profiles()}

def get_player_profiles():
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS player_profiles (player_key TEXT PRIMARY KEY, display_name TEXT NOT NULL DEFAULT '', number TEXT NOT NULL DEFAULT '', position TEXT NOT NULL DEFAULT '', photo_url TEXT NOT NULL DEFAULT '')")
        return {key: {'display_name': name, 'number': number, 'position': position, 'photo_url': photo} for key, name, number, position, photo in conn.execute('SELECT player_key,display_name,number,position,photo_url FROM player_profiles')}

class PlayerProfilePayload(BaseModel):
    player_key: str = Field(min_length=1, max_length=150)
    display_name: str = Field(default='', max_length=80)
    number: str = Field(default='', max_length=3)
    position: str = Field(default='', max_length=20)
    photo_url: str = Field(default='', max_length=1000)

@app.put('/api/admin/player')
async def save_player_profile(request: Request, payload: PlayerProfilePayload):
    if not is_admin(request):
        raise HTTPException(403, 'Acceso restringido')
    if payload.photo_url:
        from urllib.parse import urlparse
        parsed = urlparse(payload.photo_url)
        if parsed.scheme not in ('https', 'http') or not parsed.netloc:
            raise HTTPException(422, 'La foto debe ser una URL http(s) válida')
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS player_profiles (player_key TEXT PRIMARY KEY, display_name TEXT NOT NULL DEFAULT '', number TEXT NOT NULL DEFAULT '', position TEXT NOT NULL DEFAULT '', photo_url TEXT NOT NULL DEFAULT '')")
        conn.execute('INSERT OR REPLACE INTO player_profiles(player_key,display_name,number,position,photo_url) VALUES (?,?,?,?,?)', (payload.player_key, payload.display_name, payload.number, payload.position, payload.photo_url))
    return {'ok': True}


@app.get('/partidos/{match_id}', response_class=HTMLResponse)
async def match_page(request: Request, match_id: str):
    if len(match_id) > 120 or not match_id.strip():
        raise HTTPException(404, 'Partido no encontrado')
    return templates.TemplateResponse(request, 'partido.html', {'club_name': CLUB_NAME, 'match_id': match_id})

@app.get('/api/partidos/{match_id}')
async def match_data(match_id: str):
    if len(match_id) > 120 or not match_id.strip():
        raise HTTPException(404, 'Partido no encontrado')
    with lock:
        matches = list(state.get('matches') or [])
    for match in matches:
        if isinstance(match, dict) and str(match.get('matchId') or match.get('match_id') or '') == match_id:
            return {'match': match, 'club_name': CLUB_NAME, 'source': 'recent'}
    with db() as conn:
        row = conn.execute('SELECT payload FROM match_archive WHERE match_id=?', (match_id,)).fetchone()
    if row:
        return {'match': json.loads(row[0]), 'club_name': CLUB_NAME, 'source': 'archive'}
    raise HTTPException(404, 'Partido no encontrado en los datos disponibles')

@app.get('/api/health')
async def health():
    return {'status': 'ok', 'last_updated': state['updated_at'], 'api_error': state['error']}

@app.get('/login', response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, 'login.html', {'error': None})

class Credentials(BaseModel):
    username: str
    password: str

@app.post('/api/login')
async def login(request: Request, credentials: Credentials):
    if not ADMIN_PASSWORD or not SESSION_SECRET:
        raise HTTPException(503, 'Configura ADMIN_PASSWORD y SESSION_SECRET en .env')
    if not (secrets.compare_digest(credentials.username, ADMIN_USER) and secrets.compare_digest(credentials.password, ADMIN_PASSWORD)):
        raise HTTPException(401, 'Usuario o contraseña incorrectos')
    request.session.clear()
    request.session['admin'] = True
    return {'ok': True}

@app.post('/api/logout')
async def logout(request: Request):
    request.session.clear()
    return {'ok': True}

@app.get('/admin', response_class=HTMLResponse)
async def admin_page(request: Request):
    if not is_admin(request): return RedirectResponse('/login', status_code=303)
    return templates.TemplateResponse(request, 'admin.html', {'club_name': CLUB_NAME})

class SettingsPayload(BaseModel):
    title: str = Field(max_length=100, default='Los Intocables')
    subtitle: str = Field(max_length=200, default='Clubes · EA Sports FC 27')
    crest_url: str = Field(max_length=1000, default='')
    announcement: str = Field(max_length=500, default='')

@app.put('/api/admin/settings')
async def update_settings(request: Request, payload: SettingsPayload):
    if not is_admin(request): raise HTTPException(403, 'Acceso restringido')
    with db() as conn:
        for key, value in payload.model_dump().items():
            conn.execute('INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)', (key, json.dumps(value)))
    return {'ok': True, 'customization': get_settings()}

@app.post('/api/admin/refresh')
async def manual_refresh(request: Request):
    if not is_admin(request): raise HTTPException(403, 'Acceso restringido')
    await refresh()
    return {'ok': state['error'] is None, 'updated_at': state['updated_at'], 'error': state['error']}
