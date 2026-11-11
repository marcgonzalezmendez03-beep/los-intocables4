"""Clasificación conservadora de partidos FC27 frente a calendarios VPG/AFJ.

Fuentes: tabla fixtures del HUB + feeds autorizados configurados en calendarios_fuentes.json.
Solo escribe en match_labels si no hay una etiqueta manual previa.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import logging
import os
import re
import unicodedata
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from fastapi import HTTPException

LOG = logging.getLogger('intocables.auto_ligas')
TZ = ZoneInfo('Europe/Madrid')
ROOT = Path(__file__).resolve().parent
MAX_FEED_BYTES = 2_000_000
DEFAULT_SLUGS = {
    'vpg-bronze-zero': 'VPG Zero Bronze',
    'afj-cuarta': 'AFJ División 4A',
    'vpg-quinta': 'VPG División 5C',
}


# Referencias de consulta aportadas por el responsable del club.
# Una URL de referencia NO es un feed automatizado; solo url en calendarios_fuentes.json
# habilita una importación de calendario verificable (CSV/JSON/ICS).
# Horarios habituales suministrados por Los Intocables (hora peninsular española).
# No son un calendario oficial: SOLO ayudan a comprobar y desambiguar.
MATCH_SLOTS = {
    'vpg-bronze-zero': ('22:20',),
    'afj-cuarta': ('22:40',),
    'vpg-quinta': ('23:00', '23:20'),
}

COMPETITION_REFERENCES = {
    'vpg-quinta': 'https://eafcstats.es/competitions/294',
    'vpg-bronze-zero': 'https://eafcstats.es/competitions/301',
    # Enlace indicado por el usuario para AFJ División 4A.
    'afj-cuarta': 'https://www.eafcstats.es/competitions/259',
}


def competitions_catalog(configured=(), counts=None):
    configured = set(configured)
    counts = counts or {}
    return [
        {'slug':slug, 'nombre':name, 'url_referencia':COMPETITION_REFERENCES[slug],
         'calendario_conectado':slug in configured, 'horarios_habituales':list(MATCH_SLOTS[slug]),
         'partidos_clasificados':int(counts.get(slug,0))}
        for slug,name in DEFAULT_SLUGS.items()
    ]


def pick(obj, *keys):
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if obj.get(key) is not None and obj.get(key) != '':
            return obj[key]
    return None


def normalize(text):
    s = unicodedata.normalize('NFKD', str(text or '').casefold())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', s))


def parse_dt(raw, hour=None):
    if isinstance(raw, (float, int)):
        value = float(raw)
        return datetime.fromtimestamp(value / 1000 if value > 1e12 else value, timezone.utc)
    s = str(raw or '').strip()
    if not s:
        return None
    if s.isdigit():
        if len(s) in (10, 13):
            return parse_dt(int(s))
        if len(s) == 8:
            s = s[:4] + '-' + s[4:6] + '-' + s[6:]
    if re.fullmatch(r'\d{2}/\d{2}/\d{4}', s):
        s = datetime.strptime(s, '%d/%m/%Y').strftime('%Y-%m-%d')
    if hour and len(s) == 10:
        s = f'{s}T{str(hour).strip()}'
    try:
        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        return None
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)


def utc_iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def opponent_from_pair(home, away, club_name):
    a, b, team = normalize(home), normalize(away), normalize(club_name)
    if a == team and b != team:
        return str(away).strip()
    if b == team and a != team:
        return str(home).strip()
    return None


def fixture_row(item, slug, club_name):
    if not isinstance(item, dict):
        return None
    home = pick(item, 'home', 'home_team', 'homeTeam', 'team_home', 'local')
    away = pick(item, 'away', 'away_team', 'awayTeam', 'team_away', 'visitante')
    opponent = pick(item, 'opponent', 'rival', 'opponentName', 'oponente')
    if not opponent and home and away:
        opponent = opponent_from_pair(home, away, club_name)
    if not opponent or len(str(opponent).strip()) < 2:
        return None
    raw = pick(item, 'starts_at', 'dateTime', 'datetime', 'kickoff', 'start', 'fecha_hora', 'date', 'fecha')
    hh = pick(item, 'time', 'hora')
    dt = parse_dt(raw, hh)
    if not dt:
        return None
    # Fecha sin hora no basta: evita atribuir dos partidos de liga distintos al mismo encuentro.
    if isinstance(raw, str) and len(raw.strip()) == 10 and not hh:
        return None
    league = str(pick(item, 'competition_slug') or slug)
    if league != slug:
        return None
    if normalize(opponent) == normalize(club_name):
        return None
    return {'competition_slug':slug, 'opponent':str(opponent).strip(), 'starts_at':utc_iso(dt)}


def ical_unescape(s):
    return str(s).replace('\\n', ' ').replace('\\N', ' ').replace('\\,', ',').replace('\\;', ';')


def ical_opponent(summary, club_name):
    title = ical_unescape(summary)
    # Evitar interpretar jornadas con títulos sin ambos equipos.
    fragments = re.split(r'\s+(?:vs\.?|v\.)\s+|\s+[-–—]\s+', title, maxsplit=1, flags=re.I)
    if len(fragments) != 2:
        return None
    return opponent_from_pair(fragments[0], fragments[1], club_name)


def parse_ical_dt(s, key):
    s = str(s).strip()
    tz_name = re.search(r'TZID=([^;:]+)', key)
    zone = TZ
    if tz_name:
        try:
            zone = ZoneInfo(tz_name.group(1))
        except (KeyError, ValueError):
            pass
    if re.fullmatch(r'\d{8}T\d{6}Z', s):
        return datetime.strptime(s, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).astimezone(TZ)
    if re.fullmatch(r'\d{8}T\d{6}', s):
        return datetime.strptime(s, '%Y%m%dT%H%M%S').replace(tzinfo=zone).astimezone(TZ)
    if re.fullmatch(r'\d{8}T\d{4}', s):
        return datetime.strptime(s, '%Y%m%dT%H%M').replace(tzinfo=zone).astimezone(TZ)
    return None


def parse_feed(content, fmt, slug, club_name):
    text = content.decode('utf-8-sig') if isinstance(content, bytes) else str(content)
    fmt = str(fmt or '').lower().strip()
    if fmt not in ('ics', 'json', 'csv'):
        fmt = 'ics' if 'BEGIN:VCALENDAR' in text[:300] else ('json' if text.lstrip().startswith(('{','[')) else 'csv')
    if fmt == 'json':
        data = json.loads(text)
        if isinstance(data, dict):
            data = next((data[k] for k in ('fixtures','matches','partidos','events','items') if isinstance(data.get(k), list)), [])
        if not isinstance(data, list):
            raise ValueError('El calendario JSON debe contener una lista de partidos')
        return [r for item in data if (r := fixture_row(item, slug, club_name))]
    if fmt == 'csv':
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t') if text.strip() else csv.excel
        return [r for item in csv.DictReader(io.StringIO(text), dialect=dialect) if (r := fixture_row(item, slug, club_name))]
    # RFC5545 básico, admite líneas plegadas y DTSTART;TZID, sin dependencia externa.
    unfolded = re.sub(r'\r?\n[ \t]', '', text)
    entries = unfolded.split('BEGIN:VEVENT')[1:]
    result = []
    for block in entries:
        if 'END:VEVENT' not in block:
            continue
        d = {}
        for line in block.splitlines():
            if ':' in line:
                k, val = line.split(':', 1)
                d[k.upper()] = val.strip()
        title = d.get('SUMMARY', '')
        opponent = ical_opponent(title, club_name)
        start_key = next((k for k in d if k.startswith('DTSTART')), None)
        if not opponent or not start_key:
            continue
        dt = parse_ical_dt(d[start_key], start_key)
        if dt:
            result.append({'competition_slug':slug,'opponent':opponent,'starts_at':utc_iso(dt)})
    return result


def source_configs(path=None):
    path = Path(path or os.getenv('INTOCABLES_CALENDARS_FILE', str(ROOT / 'calendarios_fuentes.json')))
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, list):
        raise ValueError('calendarios_fuentes.json debe contener una lista')
    return [p for p in payload if isinstance(p, dict) and p.get('slug') in DEFAULT_SLUGS and str(p.get('url','')).strip()]


def fetch_calendar(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('La URL de calendario debe ser HTTPS pública')
    # Las URL se administran en archivos locales, no se reciben por una petición del público.
    req = Request(url, headers={'User-Agent':'LosIntocablesCalendarBot/1.0', 'Accept':'text/calendar,application/json,text/csv,text/plain'})
    with urlopen(req, timeout=12) as response:
        if urlparse(response.geturl()).scheme != 'https':
            raise ValueError('Redirección no segura')
        body = response.read(MAX_FEED_BYTES + 1)
        if len(body) > MAX_FEED_BYTES:
            raise ValueError('Calendario excesivamente grande')
    return body


def fixture_id(source, item):
    data = '\x1f'.join((source, normalize(item['opponent']), item['starts_at']))
    return hashlib.sha256(data.encode()).hexdigest()[:32]


def prepare(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS auto_fixtures (
        uid TEXT PRIMARY KEY, source TEXT NOT NULL, competition_slug TEXT NOT NULL,
        opponent TEXT NOT NULL, starts_at TEXT NOT NULL, loaded_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS auto_assignments (
        match_id TEXT PRIMARY KEY, competition_slug TEXT NOT NULL, label TEXT NOT NULL,
        fixture_uid TEXT NOT NULL, minutes_difference INTEGER NOT NULL, detected_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS auto_sources (
        source TEXT PRIMARY KEY, last_success TEXT, error TEXT, count INTEGER NOT NULL DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS slot_hints (
        match_id TEXT PRIMARY KEY, opponent TEXT NOT NULL, played_at TEXT NOT NULL,
        choices TEXT NOT NULL, detected_at TEXT NOT NULL)''')


def game_records(conn, state):
    games = {}
    for m in state.get('matches') or []:
        if isinstance(m, dict):
            ident = pick(m,'matchId','match_id')
            if ident is not None:
                games[str(ident)] = m
    for table in ('match_archive', 'match_explorer_archive'):
        try:
            rows = conn.execute(f'SELECT match_id,payload FROM {table}').fetchall()
        except Exception:
            continue
        for mid, payload in rows:
            try:
                m = json.loads(payload)
                if table == 'match_explorer_archive':
                    from match_explorer import raw_overview
                    cid = pick(state,'club_id')
                    m = raw_overview(m, cid)
                if isinstance(m, dict):
                    current = games.get(str(mid), {})
                    games[str(mid)] = {**m, **current}
            except Exception:
                continue
    result = []
    for mid, match in games.items():
        when = parse_dt(pick(match,'timestamp','date','created_at','matchDate'))
        rival = pick(match,'opponentName','opponent','opponent_name','rival')
        if when and rival and normalize(rival) not in ('rival','rival no identificado','unknown'):
            result.append({'id':mid,'opponent':str(rival),'when':when,
                           'match_type':str(pick(match,'matchType','match_type') or '')})
    return result


def similarity(a,b):
    x, y = normalize(a), normalize(b)
    if not x or not y:
        return 0
    return 1.0 if x == y else SequenceMatcher(None, x, y).ratio()


def scheduled_slot(dt, slug, tolerance_minutes=15):
    """Comprobar que el horario del calendario respeta la franja habitual del club.

    Si una jornada se mueve de horario, se podrá corregir en el panel de administración.
    """
    slots = MATCH_SLOTS.get(slug, ())
    if not slots:
        return True
    here = dt.astimezone(TZ)
    actual = here.hour*60 + here.minute
    return any(abs(actual - (int(slot[:2])*60+int(slot[3:]))) <= tolerance_minutes for slot in slots)


def slot_suggestions(game):
    """Horarios candidatos, NO pruebas de liga oficial.

    EA puede fechar el partido al inicio o al final. Preferimos el comienzo
    anterior al timestamp, pero si se solapan varias ligas informamos ambas.
    La confirmación solo se obtiene contra el rival de una jornada programada.
    """
    kind = str(game.get('match_type') or '').lower()
    if kind in ('leaguematch', 'playoffmatch'):
        return []  # Ligas internas de EA, no confundir con VPG y AFJ
    when = game.get('when')
    if when is None:
        return []
    here = when.astimezone(TZ)
    minute = here.hour * 60 + here.minute
    hints = []
    for slug, slots in MATCH_SLOTS.items():
        for slot in slots:
            start = int(slot[:2]) * 60 + int(slot[3:])
            delta = minute - start
            # Se admiten unos minutos antes (reloj EA de inicio) y hasta
            # media hora después (marcado al finalizar). No asumir certeza.
            if -5 <= delta <= 29:
                hints.append({'competition_slug': slug, 'name': DEFAULT_SLUGS[slug],
                              'slot': slot, 'minutes_from_slot': delta})
    hints.sort(key=lambda h: (0 if h['minutes_from_slot'] >= 0 else 1,
                              abs(h['minutes_from_slot'] - 15) if h['minutes_from_slot'] >= 0 else abs(h['minutes_from_slot']),
                              h['slot']))
    return hints


def match_candidates(match, fixtures, max_minutes=45):
    """Identifica partido por *rival + fecha/hora*, nunca por hora sola.

    EA puede registrar la marca de tiempo del partido al comienzo o al terminar.
    Aceptamos desde 12 min antes hasta 40 min después del inicio previsto,
    con una penalización adicional para encuentros que aún no habrían comenzado.
    Esto evita etiquetar cualquier amistoso de las 22:40 como AFJ.
    """
    out = []
    for f in fixtures:
        sim = similarity(match['opponent'], f['opponent'])
        if sim < 0.89:
            continue
        dt = parse_dt(f['starts_at'])
        if dt is None:
            continue
        if not scheduled_slot(dt, f.get('competition_slug')):
            continue
        raw_delta = (match['when'].astimezone(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds()/60
        if raw_delta < -12 or raw_delta > min(40, max_minutes):
            continue
        # Penaliza horas futuras: suele ser más fiable un encuentro ya comenzado.
        ranked_delta = raw_delta if raw_delta >= 0 else 24 + abs(raw_delta)*2
        out.append((ranked_delta, -sim, f))
    return sorted(out, key=lambda item:(item[0],item[1],item[2]['uid']))


def choose_auto(games, fixtures, max_minutes=45):
    """Un partido programado no se asigna a dos encuentros EA; ambigüedades quedan sin clasificar."""
    # El mismo encuentro puede figurar en el calendario del panel y en un feed.
    # Unificarlo para evitar falsos conflictos.
    unique_fixtures = {}
    for f in fixtures:
        k = (f['competition_slug'], normalize(f['opponent']), utc_iso(parse_dt(f['starts_at'])) if parse_dt(f['starts_at']) else f['starts_at'])
        unique_fixtures.setdefault(k, f)
    fixtures = list(unique_fixtures.values())
    proposals = []
    ambiguous = []
    for m in games:
        opts = match_candidates(m, fixtures, max_minutes)
        if not opts:
            continue
        # Si hay calendarios distintos igual de próximos, no adivinar competición.
        if len(opts) > 1 and abs(opts[1][0] - opts[0][0]) <= 15:
            ambiguous.append(m['id'])
            continue
        proposals.append((opts[0][0],m,opts[0][2]))
    proposals.sort(key=lambda t:t[0])
    used = set()
    result = []
    for minutes, m, fixture in proposals:
        if fixture['uid'] in used:
            ambiguous.append(m['id'])
            continue
        used.add(fixture['uid'])
        result.append((m,fixture,round(minutes)))
    return result, sorted(set(ambiguous))


def install(app, *, db_provider, state_getter, club_name='Los Intocables', is_admin=None, interval_minutes=10):
    """Registrar API y tarea cada 30 minutos. Llamar tras instalar match_explorer."""
    mutex = asyncio.Lock()
    status = {'at':None, 'error':None, 'assigned':0, 'ambiguous':[], 'feeds':{}}

    def update_feeds():
        sources = source_configs()
        for src in sources:
            slug, url = src['slug'], src['url']
            try:
                content = fetch_calendar(url)
                rows = parse_feed(content, src.get('format'), slug, club_name)
                if not rows:
                    raise ValueError('No hay partidos reconocibles: revisa que sea un feed de fechas, rivales y horarios, no una página JavaScript')
                timestamp = datetime.now(timezone.utc).isoformat()
                with db_provider() as conn:
                    prepare(conn)
                    known = set()
                    for f in rows:
                        ident=fixture_id(slug, f)
                        known.add(ident)
                        conn.execute('''INSERT INTO auto_fixtures(uid,source,competition_slug,opponent,starts_at,loaded_at)
                            VALUES(?,?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET opponent=excluded.opponent,starts_at=excluded.starts_at,loaded_at=excluded.loaded_at''',
                            (ident,slug,slug,f['opponent'],f['starts_at'],timestamp))
                    # Quitar partidas canceladas/reprogramadas solo tras un feed válido.
                    for (uid,) in conn.execute('SELECT uid FROM auto_fixtures WHERE source=?',(slug,)).fetchall():
                        if uid not in known:
                            conn.execute('DELETE FROM auto_fixtures WHERE uid=?',(uid,))
                    conn.execute('INSERT INTO auto_sources(source,last_success,error,count) VALUES(?,?,?,?) ON CONFLICT(source) DO UPDATE SET last_success=excluded.last_success,error=NULL,count=excluded.count',
                                 (slug,timestamp,None,len(rows)))
                status['feeds'][slug]={'ok':True,'fixtures':len(rows)}
            except Exception as e:
                status['feeds'][slug]={'ok':False,'error':f'{type(e).__name__}: {e}'}
                LOG.warning('No se ha podido importar el calendario de %s: %s',slug,e)
        return status['feeds']

    def classify():
        with db_provider() as conn:
            prepare(conn)
            try:
                manual = [dict(uid='manual:'+str(i),competition_slug=slug,opponent=op,starts_at=when)
                          for i,slug,op,when in conn.execute('SELECT id,competition_slug,opponent,starts_at FROM fixtures WHERE status NOT IN ("cancelado","aplazado")') if slug in DEFAULT_SLUGS]
            except Exception:
                manual = []
            auto = [dict(zip(('uid','competition_slug','opponent','starts_at'),row)) for row in conn.execute('SELECT uid,competition_slug,opponent,starts_at FROM auto_fixtures')]
            fixtures = manual + auto
            games = game_records(conn, state_getter() or {})
            assigned, ambiguous = choose_auto(games,fixtures)
            # Clasificación de probables: visibles en la web pero NO se
            # contabilizan como partidos de liga hasta cotejar el rival real.
            # Guardar incluso si no tenemos calendarios, para dar diagnóstico.
            confirmed_ids = {m['id'] for m, _, _ in assigned}
            now = datetime.now(timezone.utc).isoformat()
            for game in games:
                mid = game['id']
                if mid in confirmed_ids:
                    conn.execute('DELETE FROM slot_hints WHERE match_id=?', (mid,))
                    continue
                # Las etiquetas del administrador tienen prioridad total.
                manual_label = conn.execute('SELECT 1 FROM match_labels WHERE match_id=?', (mid,)).fetchone()
                if manual_label:
                    conn.execute('DELETE FROM slot_hints WHERE match_id=?', (mid,))
                    continue
                hints = slot_suggestions(game)
                if hints:
                    conn.execute('INSERT INTO slot_hints(match_id,opponent,played_at,choices,detected_at) VALUES (?,?,?,?,?) '
                        'ON CONFLICT(match_id) DO UPDATE SET opponent=excluded.opponent,played_at=excluded.played_at,choices=excluded.choices,detected_at=excluded.detected_at',
                        (mid, game['opponent'], utc_iso(game['when']), json.dumps(hints, ensure_ascii=False), now))
                else:
                    conn.execute('DELETE FROM slot_hints WHERE match_id=?', (mid,))
            total = 0
            for match, fixture, minutes in assigned:
                mid, slug = match['id'], fixture['competition_slug']
                label = DEFAULT_SLUGS[slug]
                existing = conn.execute('SELECT competition_slug,label FROM match_labels WHERE match_id=?',(mid,)).fetchone()
                previous = conn.execute('SELECT competition_slug,label FROM auto_assignments WHERE match_id=?',(mid,)).fetchone()
                # Mantener decisiones manuales sin excepción.
                if existing and (not previous or tuple(existing) != tuple(previous)):
                    continue
                conn.execute('INSERT INTO match_labels(match_id,competition_slug,label) VALUES (?,?,?) ON CONFLICT(match_id) DO UPDATE SET competition_slug=excluded.competition_slug,label=excluded.label', (mid,slug,label))
                conn.execute('INSERT INTO auto_assignments(match_id,competition_slug,label,fixture_uid,minutes_difference,detected_at) VALUES(?,?,?,?,?,?) ON CONFLICT(match_id) DO UPDATE SET competition_slug=excluded.competition_slug,label=excluded.label,fixture_uid=excluded.fixture_uid,minutes_difference=excluded.minutes_difference,detected_at=excluded.detected_at',
                             (mid,slug,label,fixture['uid'],minutes,datetime.now(timezone.utc).isoformat()))
                conn.execute('DELETE FROM slot_hints WHERE match_id=?', (mid,))
                total += 1
        status.update({'at':datetime.now(timezone.utc).isoformat(),'assigned':total,'ambiguous':ambiguous,'error':None})
        return total

    def sync():
        try:
            update_feeds()
            return classify()
        except Exception as exc:
            status['error'] = f'{type(exc).__name__}: {exc}'
            LOG.exception('Fallo en clasificador automático de ligas')
            return 0

    @app.get('/api/ligas/competiciones')
    async def lista_competiciones():
        with db_provider() as conn:
            prepare(conn)
            counts = dict(conn.execute('SELECT competition_slug,COUNT(*) FROM match_labels GROUP BY competition_slug').fetchall())
        configured = [s['slug'] for s in source_configs()]
        return {'competiciones':competitions_catalog(configured,counts),
                'nota':'Una referencia de EAFCStats no significa que haya un feed de calendario sincronizado'}

    @app.get('/api/ligas/estado')
    async def liga_health():
        with db_provider() as conn:
            prepare(conn)
            rows=conn.execute('SELECT source,last_success,error,count FROM auto_sources').fetchall()
            auto=conn.execute('SELECT COUNT(*) FROM auto_assignments').fetchone()[0]
            fixtures_count=conn.execute('SELECT COUNT(*) FROM auto_fixtures').fetchone()[0]
            hints_count=conn.execute('SELECT COUNT(*) FROM slot_hints').fetchone()[0]
            try:
                manual_count=conn.execute('SELECT COUNT(*) FROM fixtures').fetchone()[0]
            except Exception:
                manual_count=0
        configured = [s['slug'] for s in source_configs()]
        return {'ok':True,'autoclasificados_total':auto,'candidatos_sin_confirmar':hints_count,'calendarios_importados':fixtures_count,
                'calendario_panel':manual_count,'competiciones':competitions_catalog(configured),
                'fuentes_configuradas':configured,
                'fuentes':[{ 'slug':s,'last_success':ok,'error':error,'fixtures':n} for s,ok,error,n in rows],
                'sync':status,'nota':'Los horarios indicados por el club no bastan: debe coincidir también el rival de un calendario fiable'}

    @app.get('/api/ligas/partidos')
    async def liga_matches():
        with db_provider() as conn:
            prepare(conn)
            rows=conn.execute('SELECT a.match_id,a.competition_slug,a.label,a.minutes_difference,a.detected_at,l.label,l.competition_slug FROM auto_assignments a LEFT JOIN match_labels l ON l.match_id=a.match_id').fetchall()
            hints=conn.execute('SELECT match_id,opponent,played_at,choices FROM slot_hints').fetchall()
        data = {mid: {'competition_slug':manual_slug or slug, 'label':manual_label or label,
                'minutes_difference':minutes,'detected_at':detected_at,'source':('manual' if (manual_label,manual_slug)!=(label,slug) else 'auto'),
                'provisional':False} for mid,slug,label,minutes,detected_at,manual_label,manual_slug in rows}
        for mid,opponent,played_at,choices in hints:
            if mid in data:
                continue
            options=json.loads(choices)
            unique={o['competition_slug'] for o in options}
            # No fingir una liga si la ventana de tiempo admite varias.
            only=options[0] if len(unique)==1 else None
            data[mid]={'competition_slug':only['competition_slug'] if only else '',
                       'label':('Posible '+only['name']) if only else 'Liga por verificar',
                       'source':'horario','provisional':True,
                       'possible_competitions':options, 'played_at':played_at}
        return {'matches':data}

    @app.get('/api/ligas/candidatos')
    async def liga_candidates():
        with db_provider() as conn:
            prepare(conn)
            rows=conn.execute('SELECT match_id,opponent,played_at,choices,detected_at FROM slot_hints ORDER BY played_at DESC LIMIT 250').fetchall()
        return {'candidatos':[{'match_id':mid,'opponent':opp,'played_at':date,
                               'opciones':json.loads(choices),'detected_at':detected}
                              for mid,opp,date,choices,detected in rows],
                'nota':'Los candidatos por horario no están confirmados hasta cruzar el rival con un calendario de liga'}

    @app.post('/api/admin/ligas/candidatos/{match_id}/confirmar')
    async def confirm_candidate(match_id: str, request: __import__('fastapi').Request):
        if is_admin is None or not is_admin(request):
            raise HTTPException(403, 'Solo administradores')
        if len(match_id)>120:
            raise HTTPException(422, 'ID inválido')
        body=await request.json()
        slug=body.get('competition_slug') if isinstance(body,dict) else None
        if slug not in DEFAULT_SLUGS:
            raise HTTPException(422, 'Competición no válida')
        with db_provider() as conn:
            prepare(conn)
            row=conn.execute('SELECT choices FROM slot_hints WHERE match_id=?',(match_id,)).fetchone()
            if not row or slug not in {c['competition_slug'] for c in json.loads(row[0])}:
                raise HTTPException(404, 'Candidato no encontrado para esta competición')
            conn.execute('INSERT INTO match_labels(match_id,competition_slug,label) VALUES (?,?,?) '
                         'ON CONFLICT(match_id) DO UPDATE SET competition_slug=excluded.competition_slug,label=excluded.label',
                         (match_id,slug,DEFAULT_SLUGS[slug]))
            conn.execute('DELETE FROM slot_hints WHERE match_id=?',(match_id,))
        return {'ok':True,'match_id':match_id,'competition_slug':slug,'source':'admin'}

    @app.post('/api/admin/ligas/importar')
    async def import_fixture_calendar(request: __import__('fastapi').Request):
        """Importa CSV/JSON/ICS desde el panel sin depender de scraping de terceros."""
        if is_admin is None or not is_admin(request):
            raise HTTPException(403, 'Solo administradores')
        if int(request.headers.get('content-length','0') or 0)>240000:
            raise HTTPException(413,'Calendario demasiado grande')
        body=await request.json()
        slug=body.get('slug') if isinstance(body,dict) else None
        content=body.get('content') if isinstance(body,dict) else None
        fmt=body.get('format','csv') if isinstance(body,dict) else None
        if slug not in DEFAULT_SLUGS or fmt not in ('csv','json','ics') or not isinstance(content,str) or len(content)>180000:
            raise HTTPException(422,'Calendario inválido')
        try:
            parsed=parse_feed(content,fmt,slug,club_name)
        except (ValueError, csv.Error, json.JSONDecodeError) as exc:
            raise HTTPException(422, f'Formato inválido: {exc}')
        if not parsed:
            raise HTTPException(422,'No se encontraron fechas y rivales de Los Intocables en el calendario')
        source='admin-import:'+slug
        now=datetime.now(timezone.utc).isoformat()
        with db_provider() as conn:
            prepare(conn)
            conn.execute('DELETE FROM auto_fixtures WHERE source=?',(source,))
            for fixture in parsed:
                uid=fixture_id(source,fixture)
                conn.execute('INSERT INTO auto_fixtures(uid,source,competition_slug,opponent,starts_at,loaded_at) VALUES(?,?,?,?,?,?)',
                             (uid,source,slug,fixture['opponent'],fixture['starts_at'],now))
            conn.execute('INSERT INTO auto_sources(source,last_success,error,count) VALUES(?,?,?,?) '
                         'ON CONFLICT(source) DO UPDATE SET last_success=excluded.last_success,error=NULL,count=excluded.count',
                         (source,now,None,len(parsed)))
        n=await asyncio.to_thread(classify)
        return {'ok':True,'importados':len(parsed),'clasificados_en_revision':n,'competicion':DEFAULT_SLUGS[slug]}

    @app.post('/api/admin/ligas/recalcular')
    async def recalculate(request: __import__('fastapi').Request):
        if is_admin is None or not is_admin(request):
            raise HTTPException(403, 'Solo administradores')
        async with mutex:
            await asyncio.to_thread(sync)
        return {'ok':not status['error'], 'sync':status}

    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifecycle(application):
        async with previous(application):
            async def loop():
                while True:
                    try:
                        async with mutex:
                            await asyncio.to_thread(sync)
                    except Exception:
                        LOG.exception('Error de refresco de calendarios')
                    await asyncio.sleep(max(5,int(interval_minutes))*60)
            task=asyncio.create_task(loop())
            try:
                yield
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    app.router.lifespan_context = lifecycle
    return {'sync':sync,'classify':classify,'state':status}
