import asyncio, json, logging, os, secrets, sqlite3, base64, binascii
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from collections import defaultdict, deque
from urllib.parse import urlparse
from pathlib import Path
from threading import Lock
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware
try:
    from fc_clubs_api import FC27API
except ImportError:
    FC27API = None  # La web sigue funcionando con datos enviados por el bot

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
CLUB_NAME = os.getenv('CLUB_NAME', 'Los Intocables')
REFRESH_MINUTES = max(5, int(os.getenv('REFRESH_MINUTES', '5')))
ADMIN_USER = os.getenv('ADMIN_USER', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')
SESSION_SECRET = os.getenv('SESSION_SECRET', '')
DB_PATH = Path(os.getenv('DATABASE_PATH', str(ROOT / 'site.db'))).expanduser()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATA_SOURCE = os.getenv('DATA_SOURCE', 'auto').lower()
HUB_SYNC_TOKEN = os.getenv('HUB_SYNC_TOKEN', '').strip()
logger = logging.getLogger('intocables')
logging.basicConfig(level=logging.INFO)
api = FC27API(timezone='Europe/Madrid') if FC27API else None
state = {'club_id': None, 'club': None, 'overall': None, 'members': [], 'matches': [], 'updated_at': None, 'error': None, 'source': 'pending'}
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

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS player_photos (player_key TEXT PRIMARY KEY, content BLOB NOT NULL, mime TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS match_archive (match_id TEXT PRIMARY KEY, payload TEXT NOT NULL, saved_at TEXT NOT NULL)')
    conn.execute("""CREATE TABLE IF NOT EXISTS competitions (slug TEXT PRIMARY KEY, name TEXT NOT NULL, division TEXT NOT NULL DEFAULT '', website_url TEXT NOT NULL DEFAULT '', timetable TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '', sort_order INTEGER NOT NULL DEFAULT 0)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS fixtures (id INTEGER PRIMARY KEY AUTOINCREMENT, competition_slug TEXT NOT NULL DEFAULT '', opponent TEXT NOT NULL, starts_at TEXT NOT NULL, venue TEXT NOT NULL DEFAULT 'Casa', status TEXT NOT NULL DEFAULT 'programado', notes TEXT NOT NULL DEFAULT '', score_for INTEGER, score_against INTEGER)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS applications (id INTEGER PRIMARY KEY AUTOINCREMENT, alias TEXT NOT NULL, platform TEXT NOT NULL, position TEXT NOT NULL, experience TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pendiente')""")
    conn.execute("""CREATE TABLE IF NOT EXISTS match_labels (match_id TEXT PRIMARY KEY, competition_slug TEXT NOT NULL DEFAULT '', label TEXT NOT NULL DEFAULT '')""")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_settings():
    with db() as conn:
        return {k: json.loads(v) for k, v in conn.execute('SELECT key,value FROM settings')}

def fetch():
    if api is None:
        raise RuntimeError('fc-clubs-api no está instalado: instala requirements.txt o usa DATA_SOURCE=bot')
    club_id = api.find_club_id(CLUB_NAME)
    return normalized({'club_id': club_id, 'club': api.get_club_details(club_id),
      'overall': api.get_club_overall_stats(club_id), 'members': api.get_member_stats(club_id),
      'matches': api.get_club_matches(club_id, count=30),
      'updated_at': datetime.now(timezone.utc).isoformat(), 'error': None})

async def refresh():
    if DATA_SOURCE == 'bot':
        return
    try:
        data = await asyncio.to_thread(fetch)
        store_snapshot(data, source='fc27')
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
    with db() as conn:
        seeds = [
            ('vpg-bronze-zero', 'VPG Zero Bronze', 'Bronze Zero', '22:20', 0),
            ('afj-cuarta', 'AFJ División 4A', '4A', '22:40', 1),
            ('vpg-quinta', 'VPG División 5C', '5C', '23:00 · 23:20', 2),
        ]
        for slug, name, div, timetable, order in seeds:
            conn.execute('INSERT OR IGNORE INTO competitions(slug,name,division,timetable,sort_order) VALUES (?,?,?,?,?)', (slug,name,div,timetable,order))
        # Actualizar solo nombres antiguos de estas ligas, sin tocar nombres editados.
        for slug, name, div, old_names in (
            ('vpg-bronze-zero', 'VPG Zero Bronze', 'Bronze Zero', ('VPG Bronze Zero', 'VPG Zero Bronze')),
            ('afj-cuarta', 'AFJ División 4A', '4A', ('AFJ 4ª División', 'AFJ División 4A')),
            ('vpg-quinta', 'VPG División 5C', '5C', ('VPG 5ª División', 'VPG División 5C')),
        ):
            conn.execute('UPDATE competitions SET name=?, division=? WHERE slug=? AND name IN (?,?)',
                         (name, div, slug, *old_names))
    task = asyncio.create_task(poll()) if DATA_SOURCE != 'bot' else None
    if DATA_SOURCE != 'bot':
        await refresh()
    yield
    if task:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass

app = FastAPI(title='Los Intocables · FC27', lifespan=lifespan)
# Configure SESSION_SECRET in .env before exposing the site to the internet.
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET or secrets.token_urlsafe(48), same_site='lax', https_only=os.getenv('COOKIE_SECURE','false').lower()=='true')
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
templates = Jinja2Templates(directory=ROOT / 'templates')

@app.middleware('http')
async def same_origin_admin(request: Request, call_next):
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and request.url.path.startswith(('/api/admin/', '/api/login', '/api/logout')):
        origin = request.headers.get('origin')
        if origin and urlparse(origin).netloc.lower() != (request.headers.get('host') or '').lower():
            return JSONResponse({'detail': 'Origen no permitido'}, status_code=403)
    return await call_next(request)


def is_admin(request):
    return request.session.get('admin') is True

def store_snapshot(data: dict, source: str):
    # Publicamos el snapshot completo de una vez; no inferimos resultados de campos desconocidos.
    fresh = {k: data.get(k) for k in ('club_id', 'club', 'overall', 'members', 'matches', 'updated_at')}
    if not isinstance(fresh['members'], list) or not isinstance(fresh['matches'], list):
        raise ValueError('members y matches deben ser listas')
    fresh['error'] = None
    fresh['source'] = source
    payload = json.loads(json.dumps(fresh, ensure_ascii=False, default=str))
    with db() as conn:
        for m in payload['matches']:
            if not isinstance(m, dict):
                continue
            mid = m.get('matchId') or m.get('match_id')
            if mid is None:
                continue
            conn.execute('INSERT OR REPLACE INTO match_archive(match_id,payload,saved_at) VALUES (?,?,?)', (
                str(mid), json.dumps(m, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
    with lock:
        state.update(payload)

@app.post('/api/integrations/bot/snapshot')
async def ingest_bot(request: Request):
    if not HUB_SYNC_TOKEN or len(HUB_SYNC_TOKEN) < 24 or HUB_SYNC_TOKEN.startswith(('GENERA_', 'PEGA_')):
        raise HTTPException(503, 'Configura HUB_SYNC_TOKEN con al menos 24 caracteres')
    supplied = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    if not secrets.compare_digest(supplied, HUB_SYNC_TOKEN):
        raise HTTPException(401, 'Token no válido')
    if int(request.headers.get('Content-Length', '0') or '0') > 2_000_000:
        raise HTTPException(413, 'Payload demasiado grande')
    body = await request.body()
    if len(body) > 2_000_000:
        raise HTTPException(413, 'Payload demasiado grande')
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(422, 'JSON inválido')
    if not isinstance(payload, dict) or not isinstance(payload.get('members'), list) or not isinstance(payload.get('matches'), list):
        raise HTTPException(422, 'Snapshot inválido')
    store_snapshot(payload, 'discord-bot')
    return {'ok': True, 'matches': len(payload['matches']), 'updated_at': state['updated_at']}

@app.get('/', response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, 'index.html', {'club_name': CLUB_NAME, 'admin': is_admin(request)})

@app.get('/api/club')
async def club_data():
    with lock: snapshot = json.loads(json.dumps(state))
    return {**snapshot, 'customization': get_settings(), 'player_profiles': get_player_profiles(), 'match_labels': get_match_labels()}

def ensure_player_profiles(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS player_profiles (player_key TEXT PRIMARY KEY, display_name TEXT NOT NULL DEFAULT '', number TEXT NOT NULL DEFAULT '', position TEXT NOT NULL DEFAULT '', photo_url TEXT NOT NULL DEFAULT '', hidden INTEGER NOT NULL DEFAULT 0)")
    columns = {row[1] for row in conn.execute('PRAGMA table_info(player_profiles)')}
    if 'hidden' not in columns:
        conn.execute('ALTER TABLE player_profiles ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0')

def get_player_profiles():
    with db() as conn:
        ensure_player_profiles(conn)
        result = {}
        for key, name, number, position, photo, hidden in conn.execute('SELECT player_key,display_name,number,position,photo_url,hidden FROM player_profiles'):
            result[key] = {'display_name': name, 'number': number, 'position': position,
                           'photo_url': photo, 'hidden': bool(hidden)}
        return result

class PlayerProfilePayload(BaseModel):
    player_key: str = Field(min_length=1, max_length=150)
    display_name: str = Field(default='', max_length=80)
    number: str = Field(default='', max_length=3)
    position: str = Field(default='', max_length=20)
    photo_url: str = Field(default='', max_length=1000)
    hidden: bool = False

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
        ensure_player_profiles(conn)
        conn.execute('INSERT OR REPLACE INTO player_profiles(player_key,display_name,number,position,photo_url,hidden) VALUES (?,?,?,?,?,?)',
                     (payload.player_key, payload.display_name, payload.number, payload.position, payload.photo_url, int(payload.hidden)))
    return {'ok': True}

class PhotoPayload(BaseModel):
    player_key: str = Field(min_length=1, max_length=150)
    filename: str = Field(min_length=1, max_length=255)
    image_base64: str = Field(min_length=1, max_length=4500000)

def photo_type(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return 'image/png'
    if data.startswith(b'\xff\xd8\xff'): return 'image/jpeg'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP': return 'image/webp'
    if data.startswith((b'GIF87a', b'GIF89a')): return 'image/gif'
    return None

@app.post('/api/admin/player/photo')
async def upload_player_photo(request: Request, payload: PhotoPayload):
    if not is_admin(request):
        raise HTTPException(403, 'Acceso restringido')
    try:
        raw = base64.b64decode(payload.image_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, 'Imagen no válida')
    mime = photo_type(raw)
    if not mime or len(raw) > 3 * 1024 * 1024:
        raise HTTPException(422, 'Sube una imagen JPG, PNG, WEBP o GIF de máximo 3 MB')
    with db() as conn:
        conn.execute('INSERT OR REPLACE INTO player_photos(player_key,content,mime) VALUES (?,?,?)',
                     (payload.player_key, raw, mime))
        ensure_player_profiles(conn)
        conn.execute('INSERT OR IGNORE INTO player_profiles(player_key) VALUES (?)', (payload.player_key,))
        conn.execute("UPDATE player_profiles SET photo_url=? WHERE player_key=?", ('/api/player-photo/' + payload.player_key, payload.player_key))
    return {'ok': True, 'photo_url': '/api/player-photo/' + payload.player_key}

@app.get('/api/player-photo/{player_key:path}')
async def player_photo(player_key: str):
    if not player_key or len(player_key) > 150:
        raise HTTPException(404)
    with db() as conn:
        row = conn.execute('SELECT content,mime FROM player_photos WHERE player_key=?', (player_key,)).fetchone()
    if not row:
        raise HTTPException(404, 'Foto no encontrada')
    return Response(content=row[0], media_type=row[1], headers={'Cache-Control': 'no-store'})


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
    if match_id.startswith('recent-'):
        try:
            idx = int(match_id.removeprefix('recent-'))
            if 0 <= idx < len(matches) and isinstance(matches[idx], dict):
                return {'match': matches[idx], 'club_name': CLUB_NAME, 'source': 'recent', 'label': get_match_labels().get(match_id)}
        except ValueError:
            pass
    for match in matches:
        if isinstance(match, dict) and str(match.get('matchId') or match.get('match_id') or '') == match_id:
            return {'match': match, 'club_name': CLUB_NAME, 'source': 'recent', 'label': get_match_labels().get(match_id)}
    with db() as conn:
        row = conn.execute('SELECT payload FROM match_archive WHERE match_id=?', (match_id,)).fetchone()
    if row:
        return {'match': json.loads(row[0]), 'club_name': CLUB_NAME, 'source': 'archive', 'label': get_match_labels().get(match_id)}
    raise HTTPException(404, 'Partido no encontrado en los datos disponibles')

@app.get('/api/health')
async def health():
    return {'status': 'ok', 'last_updated': state['updated_at'], 'api_error': state['error'], 'source': state['source']}

@app.get('/login', response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, 'login.html', {'error': None})

class Credentials(BaseModel):
    username: str
    password: str

@app.post('/api/login')
async def login(request: Request, credentials: Credentials):
    if (not ADMIN_PASSWORD or len(ADMIN_PASSWORD) < 12 or ADMIN_PASSWORD.startswith(('CAMBIA_', 'PEGA_'))
            or not SESSION_SECRET or len(SESSION_SECRET) < 24 or SESSION_SECRET.startswith('GENERA_')):
        raise HTTPException(503, 'Configura ADMIN_PASSWORD (12+ caracteres) y SESSION_SECRET (24+) seguros en .env')
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

# ── HUB: ligas, calendario, fichajes y anotaciones de partidos ────────────────
def get_match_labels():
    with db() as conn:
        return {mid: {'competition_slug': competition, 'label': label}
                for mid, competition, label in conn.execute('SELECT match_id,competition_slug,label FROM match_labels')}

def hub_data():
    with db() as conn:
        competitions = [dict(zip(('slug','name','division','website_url','timetable','description','sort_order'), row))
                        for row in conn.execute('SELECT slug,name,division,website_url,timetable,description,sort_order FROM competitions ORDER BY sort_order,name')]
        fixtures = [dict(zip(('id','competition_slug','opponent','starts_at','venue','status','notes','score_for','score_against'), row))
                    for row in conn.execute('SELECT id,competition_slug,opponent,starts_at,venue,status,notes,score_for,score_against FROM fixtures ORDER BY starts_at ASC, id ASC')]
    return {'competitions': competitions, 'fixtures': fixtures,
            'match_labels': get_match_labels(), 'updated_at': state['updated_at'],
            'source': state['source']}

@app.get('/api/hub')
async def public_hub():
    return hub_data()

@app.get('/api/partidos')
async def match_list(limit: int = 100):
    limit = min(max(limit, 1), 200)
    with db() as conn:
        rows = conn.execute('SELECT match_id,payload,saved_at FROM match_archive ORDER BY saved_at DESC LIMIT ?', (limit,)).fetchall()
    labels = get_match_labels()
    return {'matches': [{'match_id': key, 'match': json.loads(payload), 'saved_at': saved,
                         'classification': labels.get(key)} for key, payload, saved in rows]}

@app.get('/competiciones', response_class=HTMLResponse)
async def competitions_page(request: Request):
    return templates.TemplateResponse(request, 'competitions.html', {'club_name': CLUB_NAME, 'admin': is_admin(request)})

@app.get('/fichajes', response_class=HTMLResponse)
async def recruitment_page(request: Request):
    return templates.TemplateResponse(request, 'recruitment.html', {'club_name': CLUB_NAME})

class CompetitionPayload(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    division: str = Field(default='', max_length=70)
    website_url: str = Field(default='', max_length=1000)
    timetable: str = Field(default='', max_length=100)
    description: str = Field(default='', max_length=300)
    sort_order: int = Field(default=0, ge=0, le=999)

@app.put('/api/admin/competition/{slug}')
async def edit_competition(slug: str, request: Request, payload: CompetitionPayload):
    if not is_admin(request): raise HTTPException(403, 'Acceso restringido')
    if len(slug) > 100: raise HTTPException(422, 'Identificador demasiado largo')
    if payload.website_url:
        u = urlparse(payload.website_url)
        if u.scheme not in ('https', 'http') or not u.netloc:
            raise HTTPException(422, 'La URL debe ser http(s)')
    with db() as conn:
        found = conn.execute('SELECT slug FROM competitions WHERE slug=?', (slug,)).fetchone()
        if not found: raise HTTPException(404, 'Competición no encontrada')
        conn.execute('UPDATE competitions SET name=?,division=?,website_url=?,timetable=?,description=?,sort_order=? WHERE slug=?',
                     (payload.name, payload.division, payload.website_url, payload.timetable, payload.description, payload.sort_order, slug))
    return {'ok': True}

class FixturePayload(BaseModel):
    competition_slug: str = Field(default='', max_length=100)
    opponent: str = Field(min_length=2, max_length=100)
    starts_at: str = Field(min_length=10, max_length=32)
    venue: str = Field(default='Casa', pattern='^(Casa|Fuera|Por definir)$')
    status: str = Field(default='programado', pattern='^(programado|jugado|aplazado|cancelado)$')
    notes: str = Field(default='', max_length=350)
    score_for: int | None = Field(default=None, ge=0, le=99)
    score_against: int | None = Field(default=None, ge=0, le=99)

@app.post('/api/admin/fixture')
async def create_fixture(request: Request, payload: FixturePayload):
    if not is_admin(request): raise HTTPException(403, 'Acceso restringido')
    try: datetime.fromisoformat(payload.starts_at.replace('Z', '+00:00'))
    except ValueError: raise HTTPException(422, 'Fecha inválida (ISO 8601)')
    with db() as conn:
        if payload.competition_slug and not conn.execute('SELECT 1 FROM competitions WHERE slug=?', (payload.competition_slug,)).fetchone():
            raise HTTPException(422, 'Competición desconocida')
        c = conn.execute('INSERT INTO fixtures(competition_slug,opponent,starts_at,venue,status,notes,score_for,score_against) VALUES (?,?,?,?,?,?,?,?)',
                         (payload.competition_slug, payload.opponent, payload.starts_at, payload.venue, payload.status, payload.notes, payload.score_for, payload.score_against))
        fixture_id = c.lastrowid
    return {'ok': True, 'id': fixture_id}

@app.put('/api/admin/fixture/{fixture_id}')
async def update_fixture(fixture_id: int, request: Request, payload: FixturePayload):
    if not is_admin(request): raise HTTPException(403, 'Acceso restringido')
    try: datetime.fromisoformat(payload.starts_at.replace('Z', '+00:00'))
    except ValueError: raise HTTPException(422, 'Fecha inválida')
    with db() as conn:
        if payload.competition_slug and not conn.execute('SELECT 1 FROM competitions WHERE slug=?', (payload.competition_slug,)).fetchone():
            raise HTTPException(422, 'Competición desconocida')
        c = conn.execute('UPDATE fixtures SET competition_slug=?,opponent=?,starts_at=?,venue=?,status=?,notes=?,score_for=?,score_against=? WHERE id=?',
                         (payload.competition_slug, payload.opponent, payload.starts_at, payload.venue, payload.status, payload.notes, payload.score_for, payload.score_against, fixture_id))
        if not c.rowcount: raise HTTPException(404, 'Partido no encontrado')
    return {'ok': True}

@app.delete('/api/admin/fixture/{fixture_id}')
async def remove_fixture(fixture_id: int, request: Request):
    if not is_admin(request): raise HTTPException(403, 'Acceso restringido')
    with db() as conn:
        c = conn.execute('DELETE FROM fixtures WHERE id=?', (fixture_id,))
        if not c.rowcount: raise HTTPException(404, 'Partido no encontrado')
    return {'ok': True}

class MatchLabelPayload(BaseModel):
    competition_slug: str = Field(default='', max_length=100)
    label: str = Field(default='', max_length=120)

@app.put('/api/admin/match/{match_id}/label')
async def label_match(match_id: str, request: Request, payload: MatchLabelPayload):
    if not is_admin(request): raise HTTPException(403, 'Acceso restringido')
    if not match_id or len(match_id) > 120: raise HTTPException(422, 'Identificador inválido')
    with db() as conn:
        if payload.competition_slug and not conn.execute('SELECT 1 FROM competitions WHERE slug=?', (payload.competition_slug,)).fetchone():
            raise HTTPException(422, 'Competición desconocida')
        if not payload.label and not payload.competition_slug:
            conn.execute('DELETE FROM match_labels WHERE match_id=?', (match_id,))
        else:
            conn.execute('INSERT OR REPLACE INTO match_labels(match_id,competition_slug,label) VALUES (?,?,?)', (match_id,payload.competition_slug,payload.label))
    return {'ok': True}

class ApplicationPayload(BaseModel):
    alias: str = Field(min_length=2, max_length=60)
    platform: str = Field(min_length=2, max_length=60)
    position: str = Field(min_length=2, max_length=60)
    experience: str = Field(default='', max_length=120)
    notes: str = Field(default='', max_length=1000)
    website: str = Field(default='', max_length=120)  # honeypot antispam

_application_attempts = defaultdict(deque)

@app.post('/api/fichajes/solicitud', status_code=201)
async def apply(request: Request, payload: ApplicationPayload):
    if payload.website: return {'ok': True}  # invisible honeypot; no storage
    from time import monotonic
    ip = request.client.host if request.client else 'unknown'
    now = monotonic()
    attempts = _application_attempts[ip]
    while attempts and now - attempts[0] > 3600:
        attempts.popleft()
    if len(attempts) >= 5:
        raise HTTPException(429, 'Demasiadas solicitudes. Inténtalo más tarde.')
    attempts.append(now)
    with db() as conn:
        conn.execute('INSERT INTO applications(alias,platform,position,experience,notes,created_at) VALUES (?,?,?,?,?,?)',
                     (payload.alias.strip(), payload.platform.strip(), payload.position.strip(), payload.experience.strip(), payload.notes.strip(), datetime.now(timezone.utc).isoformat()))
    return {'ok': True, 'message': 'Solicitud recibida. La revisará el administrador.'}

@app.get('/api/admin/applications')
async def admin_applications(request: Request):
    if not is_admin(request): raise HTTPException(403, 'Acceso restringido')
    with db() as conn:
        rows = conn.execute('SELECT id,alias,platform,position,experience,notes,created_at,status FROM applications ORDER BY id DESC LIMIT 300').fetchall()
    return {'applications': [dict(zip(('id','alias','platform','position','experience','notes','created_at','status'), r)) for r in rows]}

class ApplicationStatus(BaseModel):
    status: str = Field(pattern='^(pendiente|en_pruebas|aceptado|rechazado)$')

@app.patch('/api/admin/applications/{application_id}')
async def change_application(application_id: int, request: Request, payload: ApplicationStatus):
    if not is_admin(request): raise HTTPException(403, 'Acceso restringido')
    with db() as conn:
        c = conn.execute('UPDATE applications SET status=? WHERE id=?', (payload.status, application_id))
        if not c.rowcount: raise HTTPException(404, 'Solicitud no encontrada')
    return {'ok': True}


# INTOCABLES_MATCH_EXPLORER_V2
from match_explorer import install as install_match_explorer
install_match_explorer(app, state_getter=lambda: state, db_provider=db, api=api, club_name=CLUB_NAME)

# INTOCABLES_AUTO_LIGAS_V3
from league_auto import install as install_auto_ligas
install_auto_ligas(app, db_provider=db, state_getter=lambda: state, club_name=CLUB_NAME, is_admin=is_admin)
