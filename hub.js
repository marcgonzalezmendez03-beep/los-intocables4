(() => {
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const localDate=x=>{const d=new Date(x);return Number.isNaN(d.getTime())?esc(x):d.toLocaleString('es-ES',{timeZone:'Europe/Madrid',day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'});};
 const url=u=>{try{const parsed=new URL(u);return ['http:','https:'].includes(parsed.protocol)?parsed.href:null;}catch{return null;}};
 async function main(){
  try{const r=await fetch('/api/hub',{cache:'no-store'});if(!r.ok)throw Error('No se puede conectar con el calendario');const d=await r.json();
   const leagues=document.getElementById('hub-leagues');const fixtures=document.getElementById('hub-fixtures');
   const names=Object.fromEntries(d.competitions.map(c=>[c.slug,c.name]));
   if(leagues){leagues.innerHTML=d.competitions.map(c=>`<article class="hub-league-card"><div class="hub-mini-label">${esc(c.division||'COMPETICIÓN')}</div><h3>${esc(c.name)}</h3><p>${esc(c.description||'Competición oficial del club')}</p><div class="hub-league-bottom"><span>Horario habitual · ${esc(c.timetable||'Por definir')}</span>${url(c.website_url)?`<a href="${esc(url(c.website_url))}" target="_blank" rel="noopener noreferrer">Sitio oficial ↗</a>`:''}</div></article>`).join('')||'<p class="note">Aún no hay ligas configuradas.</p>';}
   if(fixtures){const list=d.fixtures.filter(m=>m.status==='programado').sort((a,b)=>a.starts_at.localeCompare(b.starts_at));const limit=location.pathname==='/competiciones'?50:4;
    fixtures.innerHTML=list.length?list.slice(0,limit).map(m=>`<div class="hub-fixture"><div class="hub-fixture-date">${localDate(m.starts_at)}<small>Hora Madrid</small></div><div class="hub-fixture-teams"><strong>LOS INTOCABLES <span>VS</span> ${esc(m.opponent)}</strong><small>${esc(names[m.competition_slug]||'Partido del club')} · ${esc(m.venue)}</small>${m.notes?`<small>${esc(m.notes)}</small>`:''}</div><span class="hub-fixture-badge">PRÓXIMO</span></div>`).join(''):'<div class="hub-empty">Aún no hay próximos partidos confirmados. El administrador puede añadirlos desde su panel.</div>';
   }
  }catch(err){for(const id of ['hub-leagues','hub-fixtures']){const el=document.getElementById(id);if(el)el.textContent=err.message;}}
 }
 main();
})();
