'use strict';
const $ = id => document.getElementById(id);
const get = (obj,...keys) => {const o=Array.isArray(obj)?obj[0]||{}:obj||{};for(const k of keys)if(o[k]!==null&&o[k]!==undefined)return o[k];return null;};
const num = x => Number(x)||0;
const val = x => x===null||x===undefined||x===''?'—':String(x);
const escapeHTML = x => String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl = url => {try {const u=new URL(url,location.origin);return ['http:','https:'].includes(u.protocol)?u.href:null;}catch{return null;}};
const formatDate = raw => {if(raw===null||raw===undefined||raw==='')return 'Fecha no disponible';let d;if(!Number.isNaN(Number(raw))&&String(raw).trim()){const t=Number(raw);d=new Date(t>1e12?t:t*1000);}else d=new Date(raw);return Number.isFinite(d.getTime())?d.toLocaleString('es-ES',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}):String(raw);};
const array = x => Array.isArray(x)?x:[];
const key = p => String(get(p,'playerName','name','personaName','persona','player')||'').trim();
const result = m => {let r=String(get(m,'result')??'').toLowerCase();if(['win','victory','w','1','victoria'].includes(r))return 'win';if(['loss','lose','l','derrota'].includes(r))return 'loss';if(['draw','tie','empate','d'].includes(r))return 'draw';const a=get(m,'goals'),b=get(m,'goalsAgainst','goalsagainst');if(a!=null&&b!=null)return num(a)>num(b)?'win':num(a)<num(b)?'loss':'draw';return 'unknown';};
const label = {win:'VICTORIA',loss:'DERROTA',draw:'EMPATE',unknown:'SIN DATO'};
const symbol={win:'V',loss:'D',draw:'E',unknown:'?'};
let snapshot={matches:[],members:[],player_profiles:{},customization:{}};
const profiles=()=>snapshot.player_profiles||{};
function profile(p){return profiles()[key(p)]||{};}
function visibleMembers(){return array(snapshot.members).filter(p=>!profile(p).hidden);}
function avatar(p){let c=profile(p),name=c.display_name||key(p)||'Jugador',src=safeUrl(c.photo_url),letter=escapeHTML(name.slice(0,2).toUpperCase());return src?`<div class="avatar"><img src="${escapeHTML(src)}" loading="lazy" alt=""></div>`:`<div class="avatar">${letter}</div>`;}
const pages=['inicio','partidos','jugadores','rankings','rendimiento'];
let activePage=null;
let transitionTimeout=null;
function moveIndicator(){
  const container=$('navigation');
  const item=container?.querySelector('a.active[data-page]');
  if(!item)return;
  const r=item.getBoundingClientRect(),b=container.getBoundingClientRect();
  container.style.setProperty('--active-y',`${item.offsetTop}px`);
  container.style.setProperty('--active-h',`${item.offsetHeight}px`);
  container.style.setProperty('--active-x',`${r.left-b.left}px`);
  container.style.setProperty('--active-w',`${r.width}px`);
  container.style.setProperty('--active-visible','1');
}
function nav(page){
  if(!pages.includes(page))page='inicio';
  const old=activePage;
  const next=$('page-'+page);
  if(!next)return;
  clearTimeout(transitionTimeout);
  const previous=old && old!==page ? $('page-'+old) : null;
  document.querySelectorAll('.section').forEach(s=>{
    s.classList.remove('page-enter','page-exit');
    if(s!==next && s!==previous)s.classList.add('hidden');
  });
  const reduceMotion=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(previous && !reduceMotion){
    document.querySelector('.layout').dataset.direction = pages.indexOf(page)<pages.indexOf(old)?'backward':'forward';
    previous.classList.remove('hidden');
    previous.classList.add('page-exit');
    previous.setAttribute('aria-hidden','true');
  }else if(previous){previous.classList.add('hidden');previous.setAttribute('aria-hidden','true');}
  next.classList.remove('hidden');
  next.removeAttribute('aria-hidden');
  if(previous && !reduceMotion)next.classList.add('page-enter');
  document.querySelectorAll('[data-page]').forEach(a=>{
    const on=a.dataset.page===page;
    a.classList.toggle('active',on);
    if(on)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');
  });
  $('current-page').textContent=({'inicio':'INICIO','partidos':'PARTIDOS','jugadores':'PLANTILLA','rankings':'RANKINGS','rendimiento':'ANÁLISIS'})[page];
  $('sidebar').classList.remove('open');
  activePage=page;
  requestAnimationFrame(moveIndicator);
  if(previous && !reduceMotion){
    transitionTimeout=setTimeout(()=>{
      previous.classList.add('hidden');
      previous.classList.remove('page-exit');
      next.classList.remove('page-enter');
    },540);
  }
  if(old!==page)window.scrollTo({top:0,behavior:'auto'});
}
window.addEventListener('hashchange',()=>nav(location.hash.slice(1)));
window.addEventListener('resize',()=>requestAnimationFrame(moveIndicator),{passive:true});
$('mobile-menu').addEventListener('click',()=>$('sidebar').classList.toggle('open'));
function leaderHTML(members,field,limit){const sorted=[...members].sort((a,b)=>num(get(b,...field))-num(get(a,...field))).slice(0,limit);return sorted.length?sorted.map((p,i)=>{const c=profile(p),name=c.display_name||key(p)||'Jugador',pos=c.position||get(p,'position')||'PLANTILLA';return `<div class="leader"><span class="leader-rank">${i+1}</span>${avatar(p)}<div class="leader-body"><b>${escapeHTML(name)}</b><small>${escapeHTML(pos)}</small></div><span class="leader-value">${escapeHTML(val(get(p,...field)))}</span></div>`;}).join(''):'<div class="empty">Sin estadísticas de jugadores disponibles.</div>';}
function matchHTML(m,index){let r=result(m),id=get(m,'matchId','match_id'),link='/partidos/'+encodeURIComponent(id!=null&&id!==''?String(id):'recent-'+index),opponent=get(m,'opponentName','opponent')||'Rival no disponible',scoreA=get(m,'goals'),scoreB=get(m,'goalsAgainst','goalsagainst'),date=get(m,'timestamp','date'),type=get(m.label,'label','competition_slug')||get(m,'competition','matchType')||'Sin clasificar';return `<a class="match-row" href="${escapeHTML(link)}" aria-label="Ver el partido contra ${escapeHTML(opponent)}"><div class="match-icon">⚽</div><div class="match-main"><b>${escapeHTML(opponent)}</b><small>${escapeHTML(formatDate(date))} · ${escapeHTML(type)}</small></div><div class="match-score">${escapeHTML(val(scoreA))} : ${escapeHTML(val(scoreB))}</div><div class="result-pill ${r}">${label[r]}</div><div class="match-arrow" title="Explorar estadísticas">↗</div></a>`;}
function makeMatches(){
  const search=$('match-search').value.trim().toLowerCase();
  const filter=$('match-filter').value;
  const competition=$('match-competition').value;
  const indexed=array(snapshot.matches).map((m,i)=>({m,i}));
  const leagueOf=m=>String(get(m.label,'competition_slug')||'sin-clasificar');
  for(const slug of ['vpg-quinta','vpg-bronze-zero','afj-cuarta']){
    const count=$('league-count-'+slug);
    if(count)count.textContent=indexed.filter(({m})=>leagueOf(m)===slug).length;
  }
  const filtered=indexed.filter(({m})=>
    (filter==='all'||result(m)===filter)&&
    (competition==='all'||leagueOf(m)===competition)&&
    [get(m,'opponentName','opponent'),get(m.label,'label','competition_slug'),get(m,'matchType','competition')]
      .some(s=>String(s||'').toLowerCase().includes(search)));
  $('matches-count').textContent=filtered.length+' partidos';
  $('all-matches').innerHTML=filtered.length?filtered.map(({m,i})=>matchHTML(m,i)).join(''):
    '<div class="empty">No hay partidos clasificados en esta selección. Se asignarán al coincidir con un calendario verificado.</div>';
}
function makePlayers(){const search=$('player-search').value.trim().toLowerCase(),field=$('player-sort').value,fields={goals:['goals'],assists:['assists'],gamesPlayed:['gamesPlayed','gamesplayed','appearances'],averageRating:['averageRating','ratingAve','rating','avgRating']};let players=visibleMembers().filter(p=>(profile(p).display_name||key(p)).toLowerCase().includes(search)).sort((a,b)=>num(get(b,...fields[field]))-num(get(a,...fields[field])));$('players-count').textContent=players.length+' jugadores';$('player-grid').innerHTML=players.length?players.map(p=>{const c=profile(p),name=c.display_name||key(p)||'Jugador',photo=safeUrl(c.photo_url),pos=c.position||get(p,'position')||'PLANTILLA',number=c.number||'—',initials=escapeHTML(name.slice(0,2).toUpperCase());return `<article class="player"><div class="player-photo">${photo?`<img src="${escapeHTML(photo)}" loading="lazy" alt="Foto de ${escapeHTML(name)}">`:initials}</div><div class="player-body"><small>#${escapeHTML(number)} · ${escapeHTML(pos)}</small><h3>${escapeHTML(name)}</h3><div class="player-stats"><span><b>${escapeHTML(val(get(p,'gamesPlayed','gamesplayed','appearances')))}</b>PJ</span><span><b>${escapeHTML(val(get(p,'goals')))}</b>GOLES</span><span><b>${escapeHTML(val(get(p,'assists')))}</b>ASIST.</span><span><b>${escapeHTML(val(get(p,'averageRating','ratingAve','rating','avgRating')))}</b>MEDIA</span></div></div></article>`;}).join(''):'<div class="empty">No hay jugadores para mostrar.</div>';}
function render(data){snapshot=data||{};const c=data.customization||{},o=Array.isArray(data.overall)?data.overall[0]||{}:data.overall||{},club=Array.isArray(data.club)?data.club[0]||{}:data.club||{},games=get(o,'gamesPlayed','gamesplayed','games'),wins=get(o,'wins'),draws=get(o,'ties','draws'),losses=get(o,'losses'),goals=get(o,'goals'),against=get(o,'goalsAgainst','goalsagainst'),rating=get(o,'skillRating','skillrating');
const displayName=String(c.title||club.clubName||'Los Intocables').toUpperCase();if(displayName==='LOS INTOCABLES'){$('club-name').innerHTML='LOS <em>INTOCABLES</em>';}else{$('club-name').textContent=displayName;}$('subtitle').textContent=c.subtitle||'Una identidad. Un equipo. Todos nuestros encuentros, números y protagonistas.';const crest=safeUrl(c.crest_url);$('club-crest').src=crest||'/static/escudo-intocables.webp';$('announcement').hidden=!c.announcement;$('announcement').textContent=c.announcement||'';
const stats={'k-games':games,'k-wins':wins,'k-goals':goals,'k-rating':rating,'l-w':wins,'l-d':draws,'l-l':losses,'perf-against':against,'perf-division':get(o,'bestDivision','bestdivision'),'perf-promotions':get(o,'promotions')};Object.entries(stats).forEach(([id,v])=>$(id).textContent=val(v));$('perf-diff').textContent=goals!=null&&against!=null?String(num(goals)-num(against)):'—';
const total=num(wins)+num(draws)+num(losses),p=total?num(wins)/total*100:0,d=total?num(draws)/total*100:0;$('win-rate').textContent=total?p.toFixed(1)+'%':'—';$('win-rate-small').textContent=total?p.toFixed(1)+'% de victorias':'Porcentaje de victorias —';$('avg-goals').textContent=num(games)&&goals!=null?(num(goals)/num(games)).toFixed(2)+' goles por partido':'Media por partido —';$('donut').style.background=total?`conic-gradient(var(--gold) 0 ${p}%,#8297a9 ${p}% ${p+d}%,var(--red) ${p+d}% 100%)`:'conic-gradient(#30343d 0 100%)';
$('last-update').textContent=data.updated_at?'Actualizado: '+formatDate(data.updated_at):'Sin actualización';$('connection').textContent=data.error?'API con incidencias':'Datos conectados';$('dot').classList.toggle('offline',!!data.error);const matches=array(data.matches);$('home-matches').innerHTML=matches.length?matches.slice(0,5).map((m,i)=>matchHTML(m,i)).join(''):'<div class="empty">Todavía no hay partidos disponibles.</div>';const form=matches.slice(0,10).map(m=>`<span class="form-chip ${result(m)}" title="${label[result(m)]}">${symbol[result(m)]}</span>`).join('');$('home-form').innerHTML=matches.length?form:'<span class="muted">No hay resultados recientes</span>';$('form-large').innerHTML=form||'<span class="muted">No hay resultados recientes</span>';
const members=visibleMembers();$('home-scorers').innerHTML=leaderHTML(members,['goals'],5);$('home-assists').innerHTML=leaderHTML(members,['assists'],5);$('rank-goals').innerHTML=leaderHTML(members,['goals'],10);$('rank-assists').innerHTML=leaderHTML(members,['assists'],10);$('rank-games').innerHTML=leaderHTML(members,['gamesPlayed','gamesplayed','appearances'],10);$('rank-rating').innerHTML=leaderHTML(members,['averageRating','ratingAve','rating','avgRating'],10);
const chart=matches.slice(0,10).reverse(),max=Math.max(1,...chart.map(m=>num(get(m,'goals'))));$('goals-chart').innerHTML=chart.length?chart.map((m,i)=>{const g=num(get(m,'goals'));return `<div class="bar-col"><span>${g}</span><div style="height:${Math.max(2,g/max*155)}px"></div><small>${i+1}</small></div>`;}).join(''):'<div class="empty">Sin goles recientes disponibles.</div>';makeMatches();makePlayers();}
async function load(){try{const res=await fetch('/api/club',{cache:'no-store'});if(!res.ok)throw Error('HTTP '+res.status);const data=await res.json();try{const history=await fetch('/api/explorador/partidos?limit=500',{cache:'no-store'});if(history.ok){const h=await history.json();if(Array.isArray(h.matches)){const combined=new Map();for(const m of array(data.matches)){const id=String(get(m,'matchId','match_id')||'');if(id)combined.set(id,m);}for(const m of h.matches){const id=String(get(m,'matchId','match_id')||'');if(id)combined.set(id,{...(combined.get(id)||{}),...m});}const d=m=>{const t=get(m,'timestamp','date');if(t===null)return 0;const n=Number(t);if(Number.isFinite(n))return n>1e12?n/1000:n;const v=Date.parse(t);return Number.isFinite(v)?v/1000:0;};data.matches=[...combined.values()].sort((a,b)=>d(b)-d(a));}}}catch(e){console.warn('El histórico ampliado aún no está disponible',e);}try{const labels=(data.match_labels||{});const rr=await fetch('/api/ligas/partidos',{cache:'no-store'});const auto=rr.ok?(await rr.json()).matches||{}:{};for(const m of array(data.matches)){const id=String(get(m,'matchId','match_id')||'');m.label=labels[id]||auto[id]||m.label||null;}const state=await fetch('/api/ligas/estado',{cache:'no-store'});if(state.ok){const e=await state.json();const output=$('auto-ligas-status');if(output)output.textContent= e.autoclasificados_total ? 'Ligas detectadas: '+e.autoclasificados_total+' partidos' : 'Ligas: sin partidos asignados todavía';}}catch(e){console.warn('Clasificación automática no disponible',e);}render(data);}catch(e){console.error('Error consultando API:',e);$('connection').textContent='Sin conexión con servidor';$('dot').classList.add('offline');$('last-update').textContent='Error de conexión';$('home-matches').innerHTML='<div class="empty">No se pudo conectar con la API. Revisa /api/health y los registros de Render.</div>';}}
$('reload').addEventListener('click',load);$('match-search').addEventListener('input',makeMatches);$('match-filter').addEventListener('change',makeMatches);$('match-competition').addEventListener('change',makeMatches);$('player-search').addEventListener('input',makePlayers);$('player-sort').addEventListener('change',makePlayers);nav(location.hash.slice(1));load();setInterval(load,60000);
