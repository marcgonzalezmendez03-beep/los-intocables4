import asyncio
import json
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote

from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import tasks
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
from fc_clubs_api import FC27API

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("fc27bot")

CLUB_NAME = os.getenv("CLUB_NAME", "Los Intocables")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0") or "0")
REFRESH_MINUTES = max(5, int(os.getenv("REFRESH_MINUTES", "5")))
DATA_FILE = Path(os.getenv("DATA_FILE", "data.json"))
HUB_URL = os.getenv("HUB_URL", "").rstrip("/")
HUB_SYNC_TOKEN = os.getenv("HUB_SYNC_TOKEN", "").strip()

api = FC27API(timezone="Europe/Madrid")
cache = {"updated_at": None, "club": None, "overall": None, "members": [], "matches": [], "error": None}
app = FastAPI(title="FC 27 Clubs Dashboard")

intents = discord.Intents.default()
bot = discord.Client(intents=intents)

def fetch_club_data():
    """Fetch public club data via the community-maintained FC27 client."""
    club_id = api.find_club_id(CLUB_NAME)
    details = api.get_club_details(club_id)
    overall = api.get_club_overall_stats(club_id)
    members = api.get_member_stats(club_id)
    matches = api.get_club_matches(club_id, count=10)

    def normalise(obj):
        if hasattr(obj, "to_dict"):
            return obj.to_dict(orient="records")
        if isinstance(obj, list):
            return [normalise(x) for x in obj]
        if isinstance(obj, dict):
            return {str(k): normalise(v) for k, v in obj.items()}
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return obj

    return {
        "club_id": club_id,
        "club": normalise(details),
        "overall": normalise(overall),
        "members": normalise(members),
        "matches": normalise(matches),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }

async def refresh_data():
    global cache
    try:
        fresh = await asyncio.to_thread(fetch_club_data)
        # Preserve only JSON-safe values in the persistent cache.
        cache = json.loads(json.dumps(fresh, default=str))
        DATA_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Datos actualizados para %s", CLUB_NAME)
        await sync_to_hub()
        await post_discord_update()
    except Exception as exc:
        log.exception("No se pudieron actualizar los datos")
        cache["error"] = f"{type(exc).__name__}: {exc}"
        cache["updated_at"] = datetime.now(timezone.utc).isoformat()

async def sync_to_hub():
    """Envía al HUB la misma instantánea que ya usa Discord; nunca envía credenciales."""
    if not HUB_URL or not HUB_SYNC_TOKEN:
        return
    def send():
        body = json.dumps(cache, ensure_ascii=False, default=str).encode('utf-8')
        request = Request(
            HUB_URL + '/api/integrations/bot/snapshot', body,
            {'Authorization': 'Bearer ' + HUB_SYNC_TOKEN, 'Content-Type': 'application/json'},
            method='POST')
        with urlopen(request, timeout=12) as response:
            return response.status
    try:
        code = await asyncio.to_thread(send)
        log.info('HUB sincronizado (HTTP %s)', code)
    except Exception:
        log.exception('No se pudieron enviar los datos al HUB; Discord seguirá funcionando')

async def post_discord_update():
    if not DISCORD_TOKEN or not DISCORD_CHANNEL_ID or not bot.is_ready():
        return
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(DISCORD_CHANNEL_ID)
        except Exception:
            log.exception("No se pudo encontrar el canal de Discord")
            return

    # Only post when recent match data changes, to avoid spamming every refresh.
    latest = (cache.get("matches") or [])
    if not latest:
        return
    match = latest[0] if isinstance(latest[0], dict) else {}
    match_id = str(match.get("matchId") or match.get("match_id") or "")
    if not match_id:
        # Unknown response shape: don't publish potentially duplicate messages.
        return
    marker_file = Path("last_posted_match.txt")
    if marker_file.exists() and marker_file.read_text(encoding="utf-8").strip() == match_id:
        return

    embed = discord.Embed(
        title=f"⚽ {CLUB_NAME} · nuevo partido detectado",
        description=f"Actualización automática de FC 27 Clubs.",
        color=0xE6FF00,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Partido ID", value=match_id, inline=False)
    if HUB_URL:
        embed.add_field(name="Ficha en Los Intocables HUB", value=f"{HUB_URL}/partidos/{quote(match_id, safe='')}", inline=False)
    embed.add_field(name="Datos", value="Consulta el panel web para ver las estadísticas disponibles.", inline=False)
    await channel.send(embed=embed)
    marker_file.write_text(match_id, encoding="utf-8")

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    safe_data = json.dumps(cache, ensure_ascii=False).replace("</", "<\\/")
    return HTMLResponse(f"""
<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FC 27 Clubs · {CLUB_NAME}</title>
<style>
:root{{--bg:#080a0a;--panel:#121616;--line:#29302b;--neon:#e6ff00;--text:#f4f6ef;--muted:#9ba59b}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(ellipse at top,#172019,#080a0a 55%);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}}
header{{padding:34px 6vw 22px;border-bottom:1px solid var(--line)}}.tag{{color:var(--neon);letter-spacing:.22em;font-size:12px;font-weight:800}}
h1{{font-size:clamp(30px,5vw,54px);margin:10px 0}}.muted{{color:var(--muted)}}main{{padding:26px 6vw 60px;max-width:1500px;margin:auto}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}}.card{{background:linear-gradient(145deg,#151b18,#0f1211);border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:0 10px 35px #0004}}
.label{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.12em}}.value{{font-size:30px;font-weight:800;margin-top:9px;color:var(--neon)}}
h2{{margin:34px 0 14px;font-size:21px}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{padding:12px 10px;text-align:left;border-bottom:1px solid var(--line)}}th{{color:var(--neon);font-size:11px;text-transform:uppercase;letter-spacing:.1em}}
.tablewrap{{overflow:auto}}.status{{margin-top:14px;font-size:12px;color:var(--muted)}}.error{{color:#ff7979}}
</style></head><body>
<header><div class="tag">PRO CLUBS · DATA CENTER</div><h1>{CLUB_NAME}</h1><div class="muted">FC 27 · Panel de estadísticas automático</div><div class="status" id="status">Cargando datos…</div></header>
<main>
<section class="grid" id="stats"></section>
<h2>Plantilla · estadísticas individuales</h2><div class="card tablewrap"><table id="members"><thead></thead><tbody></tbody></table></div>
<h2>Partidos recientes</h2><div class="card tablewrap"><table id="matches"><thead></thead><tbody></tbody></table></div>
<p class="status">Fuente comunitaria no oficial. Los datos dependen de la disponibilidad de los endpoints de EA.</p>
</main>
<script>
const d = {safe_data};
function arr(x){{if(Array.isArray(x))return x;if(x&&typeof x==='object')return Object.values(x);return []}}
function renderTable(id,rows,preferred){{
 const table=document.getElementById(id); rows=arr(rows); if(!rows.length){{table.innerHTML='<tbody><tr><td class="muted">Sin datos disponibles todavía.</td></tr></tbody>';return}}
 const keys=preferred.filter(k=>rows.some(r=>r&&r[k]!==undefined)).concat(Object.keys(rows[0]||{{}}).filter(k=>!preferred.includes(k))).slice(0,9);
 table.innerHTML='<thead><tr>'+keys.map(k=>'<th>'+k+'</th>').join('')+'</tr></thead><tbody>'+rows.slice(0,30).map(r=>'<tr>'+keys.map(k=>'<td>'+String(r?.[k]??'—').replaceAll('<','&lt;')+'</td>').join('')+'</tr>').join('')+'</tbody>';
}}
const overall=arr(d.overall)[0]||d.overall||{{}};
const metrics=[['Partidos',overall.gamesPlayed],['Victorias',overall.wins],['Empates',overall.ties],['Derrotas',overall.losses],['Goles',overall.goals],['Rating habilidad',overall.skillRating]];
document.getElementById('stats').innerHTML=metrics.map(([l,v])=>`<div class="card"><div class="label">${{l}}</div><div class="value">${{v??'—'}}</div></div>`).join('');
renderTable('members',d.members,['name','position','gamesPlayed','goals','assists','ratingAve','averageRating']);
renderTable('matches',d.matches,['timestamp','opponentName','goals','goalsAgainst','result','matchId']);
document.getElementById('status').innerHTML='Última actualización: '+(d.updated_at||'pendiente')+(d.error?' · <span class="error">'+d.error+'</span>':'');
setInterval(()=>location.reload(), 300000); // refresca el panel cada 5 minutos
</script></body></html>
""")

@app.get("/api/data")
async def get_data():
    return JSONResponse(cache)

@app.on_event("startup")
async def startup():
    if DATA_FILE.exists():
        try:
            cache.update(json.loads(DATA_FILE.read_text(encoding="utf-8")))
        except Exception:
            log.warning("No se pudo leer la caché anterior")
    await refresh_data()
    refresh_loop.start()

@app.on_event("shutdown")
async def shutdown():
    if refresh_loop.is_running():
        refresh_loop.cancel()

@tasks.loop(minutes=REFRESH_MINUTES)
async def refresh_loop():
    await refresh_data()

@bot.event
async def on_ready():
    log.info("Discord conectado como %s", bot.user)

async def main():
    web_config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")), log_level="info")
    server = uvicorn.Server(web_config)
    tasks_to_run = [server.serve()]
    if DISCORD_TOKEN:
        tasks_to_run.append(bot.start(DISCORD_TOKEN))
    else:
        log.warning("DISCORD_TOKEN no configurado: se iniciará solo la web.")
    await asyncio.gather(*tasks_to_run)

if __name__ == "__main__":
    asyncio.run(main())
