'use strict';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const v = x => x === undefined || x === null || x === '' ? '—' : String(x);
const value = x => esc(v(x));
const get = (obj, ...names) => {for (const name of names) if (obj && obj[name] !== undefined && obj[name] !== null && obj[name] !== '') return obj[name]; return null;};
const asNumber = x => x === null || x === undefined || x === '' || !Number.isFinite(Number(x)) ? null : Number(x);
const goodURL = x => {try {const url = new URL(x, location.origin); return ['https:', 'http:'].includes(url.protocol) ? url.href : null;} catch {return null;}};
const date = input => {if (input === null || input === undefined || input === '') return 'Fecha no disponible'; let raw = input, d;
  if (!Number.isNaN(Number(raw)) && String(raw).trim()) {const n = Number(raw); d = new Date(n > 1e12 ? n : n * 1000);} else d = new Date(raw);
  return Number.isNaN(d.getTime()) ? String(raw) : d.toLocaleString('es-ES', {day:'2-digit', month:'long', year:'numeric', hour:'2-digit', minute:'2-digit'});
};
const has = (p, key) => p && p.stats && p.stats[key] !== null && p.stats[key] !== undefined;
const stat = (p, key) => has(p,key) ? value(p.stats[key]) : '—';
let match = null, tab = 'resumen', side = 'all', selected = null, category = 'general', query = '';
const FIELDS = {
 general: [['goals','Goles'],['assists','Asistencias'],['rating','Valoración'],['shots','Tiros'],['shotsOnTarget','Tiros a puerta'],['secondsPlayed','Segundos jugados'],['manOfTheMatch','Jugador del partido (EA)']],
 ataque: [['goals','Goles'],['assists','Asistencias'],['shots','Tiros'],['shotsOnTarget','Tiros a puerta'],['shotsOffTarget','Tiros fuera'],['shotsOnTargetInsideBox','Tiros dentro del área'],['shotsOnTargetOutsideBox','Tiros fuera del área'],['secondAssists','Segundas asistencias'],['throughBallAssists','Asistencias con pase en profundidad'],['goalsWeakFoot','Goles con pierna mala'],['goalsFirstTime','Goles al primer toque']],
 pases: [['passesCompleted','Pases completados'],['passesAttempted','Pases intentados'],['passesFailed','Pases fallados (eventos)'],['passesCompletedForward','Pases hacia adelante'],['passesCompletedBackward','Pases hacia atrás'],['passesCompletedSideways','Pases laterales'],['passesCompletedShort','Pases cortos'],['passesCompletedMedium','Pases medios'],['passesCompletedLong','Pases largos'],['passesCompletedCross','Centros completados'],['throughPasses','Pases filtrados'],['switchesOfPlay','Cambios de orientación'],['firstTimePasses','Pases al primer toque']],
 defensa: [['tacklesWon','Entradas ganadas'],['tacklesAttempted','Entradas intentadas'],['tacklesLost','Entradas perdidas (eventos)'],['standingTacklesWon','Entradas de pie'],['slidingTacklesWon','Entradas deslizándose'],['interceptions','Intercepciones'],['opponentsDispossessed','Robos al rival'],['aerialDuelsWonDefending','Duelos aéreos defensivos'],['crossesBlocked','Centros bloqueados']],
 porteria: [['saves','Paradas'],['goalsConceded','Goles encajados'],['cleanSheets','Portería a cero'],['cleanSheetsGK','Portería a cero POR'],['goodDirectionSaves','Paradas buena dirección'],['ballDiveSaves','Paradas lanzándose'],['crossSaves','Salidas a centros'],['reflexSaves','Paradas reflejos']],
 posesion: [['dribblesCompleted','Regates completados'],['dribblesCarried','Conducciones'],['dribblesSkillMoveBeat','Regates con filigrana'],['possessionWonDefensiveThird','Recuperaciones en defensa'],['possessionWonMiddleThird','Recuperaciones en medio'],['possessionWonAttackingThird','Recuperaciones en ataque'],['possessionLostDefensiveThird','Pérdidas en defensa'],['possessionLostMiddleThird','Pérdidas en medio'],['possessionLostAttackingThird','Pérdidas en ataque']],
 disciplina: [['foulsConceded','Faltas cometidas'],['foulsWon','Faltas recibidas'],['yellowCards','Amarillas (eventos)'],['redCards','Rojas'],['penaltiesConceded','Penaltis cometidos'],['cornersTaken','Córners lanzados'],['outOfPosition','Fuera de posición (eventos)']]
};
const CAT_LABELS = {general:'General', ataque:'Ataque', pases:'Pases', defensa:'Defensa', porteria:'Portería', posesion:'Posesión', disciplina:'Disciplina'};
const compareFields = [['goals','Goles'],['shots','Tiros'],['passesCompleted','Pases completados'],['passesAttempted','Pases intentados'],['tacklesWon','Entradas ganadas'],['tacklesAttempted','Entradas intentadas'],['saves','Paradas'],['redCards','Tarjetas rojas']];
function team(index){return Array.isArray(match?.teams) ? match.teams[index] : null;}
function players(){return (match?.teams || []).flatMap((t,i) => (t.players || []).map((p,j) => ({...p, id:`${i}:${j}`, teamIndex:i, teamName:t.name, own:!!t.isOwn})));}
function formattedResult(){let r = String(match?.result || '').toLowerCase(); const a=asNumber(match?.goals), b=asNumber(match?.goalsAgainst); if (!['win','loss','draw'].includes(r) && a !== null && b !== null) r=a>b?'win':a<b?'loss':'draw'; return {win:'VICTORIA',loss:'DERROTA',draw:'EMPATE'}[r] || 'RESULTADO';}
function renderHeader(){
  $('our-name').textContent=match?.clubName || 'LOS INTOCABLES';$('opponent-name').textContent=match?.opponentName || 'RIVAL';
  $('score').textContent=`${v(match?.goals)} : ${v(match?.goalsAgainst)}`; $('match-date').textContent=date(match?.timestamp);
  const lb=match?.label || {}; $('competition').textContent=(lb.label || lb.competition_slug || match?.matchType || 'PARTIDO FC27').toString();
  $('match-id').textContent='ID DEL ENCUENTRO · '+v(match?.matchId);$('source-indicator').textContent=match?.source==='ea_raw'?'DATOS DETALLADOS CAPTURADOS DE EA':'RESUMEN DEL ARCHIVO';
  const result=formattedResult(); $('verdict').textContent=result; $('verdict').className='verdict '+({VICTORIA:'win',DERROTA:'loss',EMPATE:'draw'}[result]||'');
  const image=goodURL(match?.opponentCrestUrl || match?.opponentCrest); $('opponent-image').innerHTML=image?`<img src="${esc(image)}" alt="Escudo rival">`:'⚽';
}
function box(title,body){return `<section class="panel"><h2>${esc(title)}</h2>${body}</section>`;}
function empty(message){return `<div class="placeholder">${esc(message)}</div>`;}
function overview(){
  const own=team(0), rival=team(1), all=players(), our=all.filter(x=>x.own);
  const best=[...our].filter(p=>asNumber(p.stats.rating)!==null).sort((a,b)=>Number(b.stats.rating)-Number(a.stats.rating))[0];
  const scorers=our.filter(p=>(asNumber(p.stats.goals)||0)>0).sort((a,b)=>Number(b.stats.goals)-Number(a.stats.goals)).slice(0,5);
  const kpis=[['NUESTROS GOLES',match.goals],['GOLES RIVAL',match.goalsAgainst],['JUGADORES REGISTRADOS',all.length?all.length:null],['MEJOR VALORACIÓN',best?.stats.rating]];
  let html=`<div class="kpirow">${kpis.map(([name,n],i)=>`<div class="kpicard"><small>${esc(name)}</small><strong class="${i===0?'accent':''}">${value(n)}</strong></div>`).join('')}</div>`;
  html+='<div class="grid2">'+box('Información del encuentro',`<div class="statbox">${[['Equipo',own?.name||match.clubName],['Rival',rival?.name||match.opponentName],['Competición',match.label?.label||match.matchType],['Fecha',date(match.timestamp)],['ID oficial',match.matchId],['Origen',match.source==='ea_raw'?'API EA — datos brutos':'Histórico resumido']].map(([n,s])=>`<div><small>${esc(n)}</small><b>${value(s)}</b></div>`).join('')}</div>`)+box('Destacados del partido', our.length?`<div class="playersbrief">${best?`<div class="brief"><span class="rank">★</span><span>Mejor valoración<br><small class="muted">${esc(best.name)}</small></span><strong>${value(best.stats.rating)}</strong></div>`:''}${scorers.map(p=>`<div class="brief"><span class="rank">⚽</span><span>${esc(p.name)}<br><small class="muted">Goles</small></span><strong>${stat(p,'goals')}</strong></div>`).join('')}${!best&&!scorers.length?empty('No hay destacados individuales en esta respuesta.'):''}</div>`:empty('Este partido no tiene todavía datos individuales archivados.'))+'</div>';
  return html;
}
function comparison(){
  const a=team(0), b=team(1);
  if(!a||!b)return box('Comparación de equipos',empty('La API no proporcionó las estadísticas conjuntas de ambos clubes en este partido.'));
  const rows=compareFields.filter(([key])=>a.metrics?.[key]!=null||b.metrics?.[key]!=null);
  return box('Comparación por equipos',`<p class="subhead">${esc(a.name)} frente a ${esc(b.name)}. Solo aparecen métricas reales disponibles.</p>${rows.length?rows.map(([key,label])=>{const left=asNumber(a.metrics?.[key]),right=asNumber(b.metrics?.[key]);const total=Math.max(1,(left||0)+(right||0));return `<div class="compare-row"><b>${value(left)}</b><div class="measure">${esc(label)}<div><span class="left" style="width:${left==null?0:Math.max(2,left/total*100)}%"></span><span class="right" style="width:${right==null?0:Math.max(2,right/total*100)}%"></span></div></div><b>${value(right)}</b></div>`;}).join(''):empty('No se recibieron métricas colectivas de la API.')}`);
}
function playerProfile(p){
  if(!p)return box('Detalle individual',empty('Selecciona un jugador en la tabla para ver sus números.'));
  const fields=FIELDS[category].filter(([name])=>has(p,name));
  // Special, derived pass completion — only when both official counts exist.
  let passNote='';
  if(category==='pases' && has(p,'passesAttempted') && has(p,'passesCompleted') && p.stats.passesAttempted>0) passNote=`<div class="notice">Precisión de pase: <strong>${(100*p.stats.passesCompleted/p.stats.passesAttempted).toFixed(1)}%</strong> (pases completados / intentados).</div>`;
  const menu=Object.keys(CAT_LABELS).map(k=>`<button type="button" data-category="${k}" class="${k===category?'active':''}">${CAT_LABELS[k]}</button>`).join('');
  return `<section class="panel"><div class="profilehead"><div><strong>${esc(p.name)}</strong><br><span>${esc(p.teamName)} · ${esc(p.position)}</span></div><div class="rating">${stat(p,'rating')}</div></div><div class="subtabs">${menu}</div>${fields.length?`<div class="metriclist">${fields.map(([name,label])=>`<div class="field"><small>${esc(label)}</small><b>${stat(p,name)}</b></div>`).join('')}</div>${passNote}`:empty('EA no envió datos para esta categoría en este encuentro.')}</section>`;
}
function playerView(){
 const list=players();if(!list.length)return box('Rendimiento de los jugadores',empty('El encuentro solo dispone de un resumen. Los datos individuales se conservarán en los próximos partidos mientras esté activo el capturador del servidor.'));
 let selection=list.filter(p=>(side==='all'||(side==='ours'?p.own:!p.own))&&`${p.name} ${p.position}`.toLowerCase().includes(query.toLowerCase()));
 if(!list.find(p=>p.id===selected))selected=list[0].id;
 const current=list.find(p=>p.id===selected);
 return `<div class="filterbar"><select id="team-filter" aria-label="Filtrar equipo"><option value="all" ${side==='all'?'selected':''}>Ambos equipos</option><option value="ours" ${side==='ours'?'selected':''}>Los Intocables</option><option value="rival" ${side==='rival'?'selected':''}>Rival</option></select><input id="player-filter" aria-label="Buscar jugador" placeholder="Buscar jugador..." value="${esc(query)}"><span class="muted">${selection.length} jugadores</span></div><div class="detailslayout"><section class="panel"><h2>Plantilla del encuentro</h2><p class="subhead">Pulsa en un futbolista para explorar sus estadísticas.</p><div class="tablewrap"><table><thead><tr><th>Jugador</th><th>Posición</th><th>G</th><th>A</th><th>Nota</th></tr></thead><tbody>${selection.map(p=>`<tr class="player-row ${selected===p.id?'selected':''}" data-player="${esc(p.id)}" tabindex="0" aria-label="Explorar a ${esc(p.name)}"><td class="playername">${esc(p.name)}<small class="number">${esc(p.teamName)}</small></td><td>${esc(p.position)}</td><td>${stat(p,'goals')}</td><td>${stat(p,'assists')}</td><td>${stat(p,'rating')}</td></tr>`).join('')}</tbody></table></div></section>${playerProfile(current)}</div>`;
}
function lineups(){const ts=match.teams||[];if(!ts.length)return box('Participantes',empty('La API no facilita los jugadores de este encuentro antiguo.'));
 return `<div class="notice warn">Estas listas muestran los participantes registrados por EA y su posición, pero no una formación táctica: la API no incluye coordenadas reales de colocación.</div><div class="squads">${ts.map(t=>box(t.name,`<div class="squadhead">${t.players?.length||0} jugadores registrados</div>${t.players?.length?t.players.map(p=>`<div class="squadplayer"><span>${esc(p.name)} <small>${esc(p.position)}</small></span><b>${stat(p,'rating')}</b></div>`).join(''):empty('Sin jugadores registrados para este equipo.')}`)).join('')}</div>`;
}
function render(){if(!match)return;
 renderHeader(); document.querySelectorAll('[data-tab]').forEach(btn=>btn.classList.toggle('active',btn.dataset.tab===tab));
 $('main-content').innerHTML=({resumen:overview,estadisticas:comparison,jugadores:playerView,alineaciones:lineups}[tab]||overview)();
 const filter=$('team-filter'); if(filter)filter.addEventListener('change',e=>{side=e.target.value;render();});
 const search=$('player-filter'); if(search)search.addEventListener('input',e=>{const pos=e.target.selectionStart;query=e.target.value;render();const input=$('player-filter');if(input){input.focus();input.setSelectionRange(pos,pos);}});
 document.querySelectorAll('[data-player]').forEach(node=>{const go=()=>{selected=node.dataset.player;render();};node.addEventListener('click',go);node.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go();}});});
 document.querySelectorAll('[data-category]').forEach(node=>node.addEventListener('click',()=>{category=node.dataset.category;render();}));
}
document.querySelectorAll('[data-tab]').forEach(btn=>btn.addEventListener('click',()=>{tab=btn.dataset.tab;render();}));
(async()=>{
  try {
    const path='/api/explorador/partidos/'+encodeURIComponent(window.MATCH_ID);
    const res=await fetch(path,{cache:'no-store'});
    if(!res.ok){let msg='HTTP '+res.status;try{msg=(await res.json()).detail||msg;}catch{}throw Error(msg);}
    match=await res.json();
    if(match.source==='ea_raw'){$('status').textContent='';}
    else{$('status').className='notice warn';$('status').textContent=match.notice||'Solo se conserva un resumen de este partido. La API no facilita sus datos individuales antiguos.';}
    render();
  } catch(e){$('status').className='notice error';$('status').textContent='No se pudieron cargar los detalles: '+e.message+'. Comprueba la instalación de match_explorer.py en el servidor.';}
})();
