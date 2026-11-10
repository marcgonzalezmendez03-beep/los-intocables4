"""Explorador de partidos FC27 para la web Los Intocables.

Módulo aditivo: no altera las rutas ni las tablas ya existentes de main.py.
Guarda la respuesta JSON *completa* de clubs/matches (jugadores + aggregate)
para que se pueda profundizar en cada partido más tarde.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import HTTPException

try:
    from fc_clubs_api.events import decode_events
except ImportError:
    def decode_events(_player):
        return {}

LOG = logging.getLogger('intocables.explorador')
MATCH_TYPES = ('leagueMatch', 'friendlyMatch', 'playoffMatch')


def pick(obj, *names):
    if not isinstance(obj, dict):
        return None
    for name in names:
        if name in obj and obj[name] is not None and obj[name] != '':
            return obj[name]
    return None


def number(value):
    if value is None or value == '':
        return None
    try:
        val = float(value)
    except (ValueError, TypeError):
        return None
    if val != val or abs(val) == float('inf'):
        return None
    return int(val) if val.is_integer() else round(val, 3)


def matches_list(value):
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


def raw_players(raw, club_id):
    collection = (raw.get('players') or {}) if isinstance(raw.get('players'), dict) else {}
    players = collection.get(str(club_id), {})
    if isinstance(players, list):
        entries = [(str(i), p) for i, p in enumerate(players)]
    elif isinstance(players, dict):
        entries = players.items()
    else:
        entries = []
    result = []
    for player_id, player in entries:
        if not isinstance(player, dict):
            continue
        try:
            has_events = any(str(player.get(f'match_event_aggregate_{i}') or '').strip() for i in range(4))
            decoded = (decode_events(player) or {}) if has_events else {}
        except (KeyError, TypeError, ValueError):
            decoded = {}
        stats = {}
        # Convert EA's lowercase field names to the known names used by the UI.
        fields = {
            'goals': ('goals',), 'assists': ('assists',), 'rating': ('rating', 'matchRating'),
            'shots': ('shots',), 'shotsOnTarget': ('shotsontarget', 'shotsOnTarget'),
            'passesAttempted': ('passattempts', 'passesAttempted'),
            'passesCompleted': ('passesmade', 'passesMade'),
            'tacklesAttempted': ('tackleattempts', 'tacklesAttempted'),
            'tacklesWon': ('tacklesmade', 'tacklesMade'),
            'saves': ('saves',), 'goalsConceded': ('goalsconceded', 'goalsConceded'),
            'redCards': ('redcards', 'redCards'),
            'secondsPlayed': ('secondsPlayed', 'gameTime'),
            'cleanSheets': ('cleansheetsany',), 'cleanSheetsDef': ('cleansheetsdef',),
            'cleanSheetsGK': ('cleansheetsgk',), 'manOfTheMatch': ('mom',)
        }
        for target, options in fields.items():
            n = number(pick(player, *options))
            if n is not None:
                stats[target] = n
        # Extra detailed actions decoded from the published fc-clubs-api mapping.
        # Authoritative EA totals win if both exist; events are best used for breakdowns.
        for key, value in decoded.items():
            n = number(value)
            if n is not None:
                stats.setdefault(key, n)
        result.append({
            'playerId': str(player_id),
            'name': str(pick(player, 'playername', 'playerName', 'name') or f'Jugador {player_id}'),
            'position': str(pick(player, 'pos', 'position') or '—'),
            'stats': stats,
        })
    return sorted(result, key=lambda p: (-(number(p['stats'].get('rating')) or 0), p['name'].casefold()))


def raw_overview(raw, own_club_id=None, type_hint=None, default_club='Los Intocables'):
    clubs = raw.get('clubs') or {}
    if not isinstance(clubs, dict):
        clubs = {}
    club_ids = list(clubs)
    ours = str(own_club_id) if own_club_id is not None else ''
    if ours not in clubs:
        ours = next((cid for cid, c in clubs.items()
                     if str(pick(c.get('details', {}), 'name') or '').casefold() == default_club.casefold()), '')
    if ours not in clubs and club_ids:
        ours = club_ids[0]
    other = next((cid for cid in club_ids if cid != ours), None)
    own = clubs.get(ours, {})
    opp = clubs.get(other, {}) if other else {}
    own_name = pick(own.get('details') or {}, 'name') or default_club
    opp_name = pick(opp.get('details') or {}, 'name') or 'Rival no identificado'
    own_goals = number(pick(own, 'goals', 'score'))
    opp_goals = number(pick(opp, 'goals', 'score'))
    if opp_goals is None:
        opp_goals = number(pick(own, 'goalsAgainst'))
    res = 'unknown'
    if own_goals is not None and opp_goals is not None:
        res = 'win' if own_goals > opp_goals else ('loss' if own_goals < opp_goals else 'draw')
    aggregates = raw.get('aggregate') if isinstance(raw.get('aggregate'), dict) else {}
    teams = []
    for cid in (ours, other):
        if not cid:
            continue
        obj = clubs.get(cid) or {}
        aggr = aggregates.get(cid, {})
        if not isinstance(aggr, dict):
            aggr = {}
        mapped = {
            'shots': ('shots',), 'passesAttempted': ('passattempts',),
            'passesCompleted': ('passesmade',), 'tacklesAttempted': ('tackleattempts',),
            'tacklesWon': ('tacklesmade',), 'saves': ('saves',),
            'redCards': ('redcards',), 'goalsConceded': ('goalsconceded',),
        }
        metrics = {key: number(pick(aggr, *names)) for key, names in mapped.items()}
        metrics = {k: v for k, v in metrics.items() if v is not None}
        metrics['goals'] = number(pick(obj, 'goals', 'score'))
        teams.append({
            'id': str(cid),
            'name': pick(obj.get('details') or {}, 'name') or (default_club if cid == ours else 'Rival'),
            'goals': number(pick(obj, 'goals', 'score')),
            'metrics': metrics,
            'players': raw_players(raw, cid),
            'isOwn': cid == ours,
        })
    return {
        'matchId': str(pick(raw, 'matchId', 'match_id') or ''),
        'timestamp': pick(raw, 'timestamp', 'date'),
        'matchType': type_hint or pick(raw, 'matchType') or 'leagueMatch',
        'opponentName': opp_name,
        'goals': own_goals,
        'goalsAgainst': opp_goals,
        'result': res,
        'teams': teams,
        'hasPlayers': any(t['players'] for t in teams),
        'clubName': own_name,
    }


def date_score(value):
    if value is None:
        return 0
    try:
        x = float(value)
        return x / 1000 if x > 1e12 else x
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
        except ValueError:
            return 0


def install(app, *, state_getter, db_provider, api, club_name):
    """Añade rutas + capturador periódico sin tocar otros endpoints.

    La instalación debe ocurrir AL FINAL de main.py, una vez declaradas rutas/funciones.
    db_provider es la función db() ya existente (contextmanager sqlite3).
    """
    interval = max(5, min(120, int(os.getenv('EXPLORER_REFRESH_MINUTES', '10')))) * 60
    cached_club_id = [None]
    sync_lock = asyncio.Lock()
    last_sync = {'at': None, 'error': None}

    def prepare(conn):
        conn.execute('''CREATE TABLE IF NOT EXISTS match_explorer_archive (
            match_id TEXT PRIMARY KEY,
            club_id TEXT NOT NULL,
            match_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            captured_at TEXT NOT NULL
        )''')

    def club_id():
        current = state_getter() or {}
        cid = current.get('club_id') or cached_club_id[0]
        if not cid and api is not None:
            cid = api.find_club_id(club_name)
        if cid:
            cached_club_id[0] = str(cid)
        return str(cid) if cid else None

    def sync_raw(match_types=MATCH_TYPES):
        if api is None:
            return 0
        cid = club_id()
        if not cid:
            return 0
        count, failures = 0, []
        for match_type in match_types:
            try:
                # RAW es esencial: get_club_matches() normalizado descarta los jugadores.
                rows = api.get_club_matches(cid, match_type=match_type, count=10, output='raw')
                rows = matches_list(rows)
                with db_provider() as conn:
                    prepare(conn)
                    for m in rows:
                        mid = pick(m, 'matchId', 'match_id')
                        if mid is None:
                            continue
                        conn.execute('''INSERT INTO match_explorer_archive(match_id,club_id,match_type,payload,captured_at)
                            VALUES(?,?,?,?,?) ON CONFLICT(match_id) DO UPDATE SET
                            club_id=excluded.club_id, match_type=excluded.match_type,
                            payload=excluded.payload, captured_at=excluded.captured_at''',
                            (str(mid), cid, match_type, json.dumps(m, ensure_ascii=False, default=str),
                             datetime.now(timezone.utc).isoformat()))
                        count += 1
            except Exception as exc:
                failures.append(f'{match_type}: {type(exc).__name__}: {exc}')
                LOG.warning('No se pudieron obtener %s: %s', match_type, exc)
        last_sync['at'] = datetime.now(timezone.utc).isoformat()
        last_sync['error'] = '; '.join(failures) or None
        return count

    def resolve_summary(mid):
        state = state_getter() or {}
        ms = matches_list(state.get('matches'))
        if mid.startswith('recent-'):
            try:
                i = int(mid.split('-', 1)[1])
                if 0 <= i < len(ms):
                    return ms[i]
            except (ValueError, IndexError):
                pass
        for m in ms:
            if str(pick(m, 'matchId', 'match_id')) == mid:
                return m
        with db_provider() as conn:
            try:
                row = conn.execute('SELECT payload FROM match_archive WHERE match_id=?', (mid,)).fetchone()
                return json.loads(row[0]) if row else None
            except Exception:
                return None

    def get_raw(mid):
        with db_provider() as conn:
            prepare(conn)
            row = conn.execute('SELECT payload, club_id, match_type FROM match_explorer_archive WHERE match_id=?', (mid,)).fetchone()
        if row:
            return json.loads(row[0]), row[1], row[2]
        return None

    def get_label(mid):
        with db_provider() as conn:
            try:
                row = conn.execute('SELECT label,competition_slug FROM match_labels WHERE match_id=?', (mid,)).fetchone()
            except Exception:
                return None
        if row:
            return {'label': row[0], 'competition_slug': row[1]}
        return None

    def detail(mid):
        summary = resolve_summary(mid)
        real_id = str(pick(summary, 'matchId', 'match_id') or mid)
        raw_result = get_raw(real_id)
        if raw_result:
            raw, cid, kind = raw_result
            overview = raw_overview(raw, cid, kind, club_name)
            # Normalized rows may contain fields not in the raw response (crest, result, etc.).
            if isinstance(summary, dict):
                for name in ('opponentCrestUrl', 'opponentCrest', 'dnf'):
                    if name in summary:
                        overview[name] = summary[name]
            overview.update({'source': 'ea_raw', 'label': get_label(real_id)})
            return overview
        if summary:
            result = dict(summary)
            result['matchId'] = str(pick(result, 'matchId', 'match_id') or mid)
            result.update({'teams': [], 'hasPlayers': False, 'source': 'resumen',
                           'label': get_label(real_id),
                           'notice': 'El archivo contiene solo el resumen de este partido. EA no permite recuperar encuentros antiguos fuera de los 10 recientes por tipo.'})
            return result
        raise HTTPException(status_code=404, detail='Partido no encontrado en el archivo disponible')

    @app.get('/api/explorador/partidos')
    async def explore_matches(limit: int = 150):
        limit = max(1, min(limit, 500))
        combined = {}
        state = state_getter() or {}
        for i, m in enumerate(matches_list(state.get('matches'))):
            mid = str(pick(m, 'matchId', 'match_id') or f'recent-{i}')
            combined[mid] = {**m, 'matchId': mid, 'hasPlayers': bool(m.get('players'))}
        with db_provider() as conn:
            prepare(conn)
            try:
                old = conn.execute('SELECT match_id,payload FROM match_archive').fetchall()
            except Exception:
                old = []
            raw = conn.execute('SELECT match_id,payload,club_id,match_type FROM match_explorer_archive').fetchall()
        for mid, payload in old:
            try:
                m = json.loads(payload)
                if isinstance(m, dict):
                    combined.setdefault(mid, {**m, 'matchId': str(mid), 'hasPlayers': bool(m.get('players'))})
            except ValueError:
                continue
        for mid, payload, cid, kind in raw:
            try:
                raw_info = raw_overview(json.loads(payload), cid, kind, club_name)
            except (TypeError, ValueError):
                continue
            existing = combined.get(str(mid), {})
            combined[str(mid)] = {**existing, **{k: v for k, v in raw_info.items() if k != 'teams'}}
        items = sorted(combined.values(), key=lambda m: date_score(pick(m, 'timestamp', 'date')), reverse=True)
        return {'matches': items[:limit], 'total': len(items), 'last_sync': last_sync}

    @app.get('/api/explorador/partidos/{match_id}')
    async def explore_match(match_id: str):
        if not match_id.strip() or len(match_id) > 120:
            raise HTTPException(404, 'ID de partido inválido')
        result = detail(match_id)
        # Evita disparar múltiples consultas contra EA por cada visita pública.
        # Si el capturador acaba de consultar EA, abrir un partido antiguo no
        # puede recuperarlo de un historial que EA ya no sirve.
        recent_poll = bool(last_sync['at'] and (datetime.now(timezone.utc).timestamp() - date_score(last_sync['at']) < 300))
        if result['source'] != 'ea_raw' and api is not None and not recent_poll:
            async with sync_lock:
                recent_poll = bool(last_sync['at'] and (datetime.now(timezone.utc).timestamp() - date_score(last_sync['at']) < 300))
                if not recent_poll:
                    await asyncio.to_thread(sync_raw, MATCH_TYPES[:2])
            result = detail(match_id)
        return result

    @app.get('/api/explorador/estado')
    async def explorer_health():
        with db_provider() as conn:
            prepare(conn)
            n = conn.execute('SELECT COUNT(*) FROM match_explorer_archive').fetchone()[0]
        return {'ok': True, 'partidos_detallados_guardados': n, 'last_sync': last_sync,
                'api_disponible': api is not None}

    # Compatibilidad con aplicaciones que usan FastAPI(lifespan=...), donde los
    # handlers clásicos @app.on_event('startup') no se ejecutan.
    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def enhanced_lifespan(application):
        async with previous_lifespan(application):
            async def worker():
                while True:
                    try:
                        async with sync_lock:
                            await asyncio.to_thread(sync_raw)
                    except Exception:
                        LOG.exception('Fallo inesperado al actualizar partidos')
                    await asyncio.sleep(interval)
            task = asyncio.create_task(worker()) if api is not None else None
            try:
                yield
            finally:
                if task:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

    app.router.lifespan_context = enhanced_lifespan
    return {'sync_raw': sync_raw, 'detail': detail}
