const $ = id => document.getElementById(id);
const escapeHtml = v => String(v ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const get = (o,...keys) => {for(const k of keys){if(o && o[k]!==undefined && o[k]!==null && o[k]!=='')return o[k];}return null;};
const fmt = v => v===null||v===undefined||v===''?'—':escapeHtml(v);
const validUrl = u => {try{const p=new URL(u);return ['http:','https:'].includes(p.protocol)?p.href:null;}catch{return null;}};
let match = null, active='resumen';
const teams = () => {
  const a=get(match,'homeTeam','home','clubStats','clubs');
  return a && typeof a==='object' ? a : null;
};
const playerArrays = () => {
  // Distintas versiones de API pueden devolver listas de jugadores con claves diferentes.
  const source = get(match,'players','playerStats','members','lineups','lineup');
  if(Array.isArray(source))return {ours:source,theirs:[]};
  if(source && typeof source==='object'){
    const ours=get(source,'home','homePlayers','ours','team1','players');
    const theirs=get(source,'away','awayPlayers','opponent','team2');
    return {ours:Array.isArray(ours)?ours:[],theirs:Array.isArray(theirs)?theirs:[]};
  }
  return {ours:[],theirs:[]};
};
function panel(title,body){return `<section class="panel"><h3>${escapeHtml(title)}</h3>${body}</section>`;}
function empty(text){return `<div class="empty">${escapeHtml(text)}</div>`;}
function render(){if(!match)return;
 const ours='Los Intocables', rival=get(match,'opponentName','opponent')||'Rival';
 $('home').textContent=ours;$('away').textContent=rival;
 $('score').textContent=`${get(match,'goals')??'—'} - ${get(match,'goalsAgainst','goalsagainst')??'—'}`;
 const rawDate=get(match,'timestamp','date');let dt='Fecha no disponible';if(rawDate){const d=new Date(rawDate);dt=isNaN(d)?String(rawDate):d.toLocaleString('es-ES',{dateStyle:'medium',timeStyle:'short'});}
 $('date').textContent=dt;
 $('type').textContent='FC 27 · '+(get(match,'matchType','competition','type')||'PARTIDO');
 const crest=validUrl(get(match,'opponentCrestUrl','opponentCrest','crestUrl'));
 $('rival-crest').classList.toggle('hidden',!crest);$('crest-fallback').classList.toggle('hidden',!!crest);if(crest)$('rival-crest').src=crest;
 document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===active));
 let html='';
 if(active==='resumen'){
  const fields=[['Resultado',get(match,'result')],['Competición',get(match,'matchType','competition')],['Fecha',dt],['ID del partido',get(match,'matchId','match_id')],['DNF',get(match,'dnf')===true?'Sí':get(match,'dnf')===false?'No':null]];
  html=panel('Resumen del encuentro',`<div class="grid">${fields.map(([k,v])=>`<div class="stat"><small>${escapeHtml(k)}</small><strong>${fmt(v)}</strong></div>`).join('')}</div>`);
 }else if(active==='alineaciones'){
  const {ours,theirs}=playerArrays();
  const side=(name,list)=>`<div class="pitch"><h3>${escapeHtml(name)}</h3>${list.length?list.map(p=>`<div class="player"><span>${fmt(get(p,'playerName','name','personaName'))}</span><small>${fmt(get(p,'position','pos'))} · ${fmt(get(p,'rating','ratingAve','matchRating'))}</small></div>`).join(''):empty('La API no proporciona la alineación de este equipo en los datos de este partido.')}</div>`;
  html=panel('Alineaciones y jugadores',`<div class="teams">${side(ours,ours)}${side(rival,theirs)}</div>`);
 }else if(active==='estadisticas'){
  const fields=[['Goles a favor',get(match,'goals')],['Goles en contra',get(match,'goalsAgainst','goalsagainst')],['Tiros',get(match,'shots','shotsFor')],['Tiros a puerta',get(match,'shotsOnTarget')],['Posesión',get(match,'possession')],['Pases',get(match,'passes')],['Faltas',get(match,'fouls')],['Córners',get(match,'corners')]];
  html=panel('Estadísticas del partido',`<div class="grid">${fields.map(([k,v])=>`<div class="stat"><small>${escapeHtml(k)}</small><strong>${fmt(v)}</strong></div>`).join('')}</div><p class="notice">Un guion significa que la API no incluye esa estadística para este encuentro.</p>`);
 }else{
  const {ours,theirs}=playerArrays();const players=[...ours.map(p=>({...p,_team:'Los Intocables'})),...theirs.map(p=>({...p,_team:rival}))];
  html=panel('Rendimiento individual',players.length?`<div style="overflow-x:auto"><table><thead><tr><th>Jugador</th><th>Posición</th><th>Goles</th><th>Asistencias</th><th>Valoración</th></tr></thead><tbody>${players.map(p=>`<tr><td>${fmt(get(p,'playerName','name','personaName'))}</td><td>${fmt(get(p,'position','pos'))}</td><td>${fmt(get(p,'goals'))}</td><td>${fmt(get(p,'assists'))}</td><td>${fmt(get(p,'rating','ratingAve','matchRating'))}</td></tr>`).join('')}</tbody></table></div>`:empty('La API no incluye estadísticas individuales para este partido.'));
 }
 $('content').innerHTML=html;
}
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>{active=b.dataset.tab;render();}));
(async()=>{try{const r=await fetch('/api/partidos/'+encodeURIComponent(window.MATCH_ID),{cache:'no-store'});if(!r.ok)throw new Error('Partido no encontrado (HTTP '+r.status+')');const d=await r.json();match=d.match;$('message').textContent='';render();}catch(e){$('message').textContent=e.message+' · Vuelve al listado de partidos.';}})();
