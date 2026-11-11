const $ = id => document.getElementById(id);
const value = (o, ...keys) => {
  if (Array.isArray(o)) o = o[0] || {};
  for (const k of keys) if (o && o[k] !== undefined && o[k] !== null) return o[k];
  return null;
};
const n = x => Number(x) || 0;
const show = x => x === null || x === undefined || x === '' ? '—' : x;
const safeUrl = u => { try { const x = new URL(u, location.origin); return ['http:','https:'].includes(x.protocol) ? x.href : null; } catch { return null; } };
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const dateText = input => {
  if (!input) return 'Fecha no disponible';
  const d = new Date(input);
  if (isNaN(d)) return String(input);
  return d.toLocaleString('es-ES', {day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit'});
};

function resultInfo(result){
  const r = String(result || '').toLowerCase();
  if (r === 'win') return {cls:'win', label:'VICTORIA', short:'V'};
  if (r === 'loss') return {cls:'loss', label:'DERROTA', short:'D'};
  return {cls:'draw', label:'EMPATE', short:'E'};
}

function renderRankList(targetId, players, statKey, statLabel){
  const target = $(targetId);
  target.replaceChildren();
  const sorted = players.slice().sort((a,b)=> n(value(b, statKey)) - n(value(a, statKey))).filter(p => n(value(p, statKey)) > 0).slice(0,5);
  if (!sorted.length){
    target.innerHTML = '<div class="empty-state">Sin datos suficientes todavía.</div>';
    return;
  }
  sorted.forEach((p, i) => {
    const row = document.createElement('div');
    row.className = 'ranking-item';
    row.innerHTML = `
      <div class="rank-pill">${i+1}</div>
      <div>
        <strong>${esc(value(p,'playerName','name') || 'Jugador')}</strong>
        <span>${esc(value(p,'position') || 'Sin posición')} · ${esc(statLabel)}</span>
      </div>
      <div class="ranking-value">${show(value(p, statKey))}</div>
    `;
    target.append(row);
  });
}

function render(data){
  const c = data.customization || {};
  const o = Array.isArray(data.overall) ? data.overall[0] || {} : data.overall || {};
  const club = Array.isArray(data.club) ? data.club[0] || {} : data.club || {};

  $('club-title').textContent = (c.title || club.clubName || 'Los Intocables').toUpperCase();
  $('subtitle').textContent = c.subtitle || 'Rendimiento, resultados y estadísticas del club con una presentación limpia y profesional.';

  const crest = safeUrl(c.crest_url) || '/static/escudo-intocables.webp';
  if (crest) {
    $('crest').src = crest;
    $('crest-frame').classList.remove('hidden');
  } else {
    $('crest-frame').classList.add('hidden');
  }

  if (c.announcement) {
    $('announcement').textContent = c.announcement;
    $('announcement').classList.remove('hidden');
  } else {
    $('announcement').classList.add('hidden');
  }

  const games = value(o,'gamesPlayed','gamesplayed','games');
  const wins = value(o,'wins');
  const ties = value(o,'ties','draws');
  const losses = value(o,'losses');
  const goals = value(o,'goals');
  const against = value(o,'goalsAgainst','goalsagainst');
  const rating = value(o,'skillRating','skillrating');
  const bestDivision = value(o,'bestDivision','bestdivision');
  const promotions = value(o,'promotions');

  for (const [id, v] of Object.entries({games, wins, goals, rating, against, promotions})) {
    if ($(id)) $(id).textContent = show(v);
  }
  $('best-division').textContent = show(bestDivision);
  $('diff').textContent = goals == null || against == null ? '—' : n(goals) - n(against);

  const total = Math.max(1, n(wins) + n(ties) + n(losses));
  const winPct = n(games) ? (100 * n(wins) / n(games)).toFixed(1) + '%' : '—';
  $('winpct').textContent = winPct;
  $('record-w').textContent = show(wins);
  $('record-d').textContent = show(ties);
  $('record-l').textContent = show(losses);
  const winPercentValue = Math.min(100, (100 * n(wins) / total));
  const drawPercentValue = Math.min(100, (100 * n(ties) / total));
  const lossPercentValue = Math.min(100, (100 * n(losses) / total));
  $('winbar').style.width = winPercentValue + '%';
  $('drawbar').style.width = drawPercentValue + '%';
  $('lossbar').style.width = lossPercentValue + '%';
  document.documentElement.style.setProperty('--winpct', winPercentValue + '%');

  $('updated').textContent = data.updated_at ? 'Actualizado · ' + new Date(data.updated_at).toLocaleString('es-ES') : 'Esperando actualización';
  $('status').textContent = data.error ? 'Últimos datos cargados · conexión con incidencias' : 'Datos conectados correctamente';
  $('status-dot').classList.toggle('offline', !!data.error);

  const recentForm = $('recent-form');
  if (recentForm) {
    recentForm.replaceChildren();
    const recent = Array.isArray(data.matches) ? data.matches.slice(0, 5).reverse() : [];
    if (recent.length) {
      const label = document.createElement('span'); label.className = 'form-label'; label.textContent = 'ÚLTIMOS 5'; recentForm.append(label);
      recent.forEach(m => {
        const result = resultInfo(value(m, 'result'));
        const chip = document.createElement('span'); chip.className = 'form-result ' + result.cls;
        chip.textContent = result.short; chip.title = result.label;
        recentForm.append(chip);
      });
    }
  }

  const matches = $('matches');
  matches.replaceChildren();
  const list = Array.isArray(data.matches) ? data.matches : [];
  if (!list.length) {
    matches.innerHTML = '<div class="empty-state">No hay partidos disponibles todavía.</div>';
  } else {
    list.forEach((m, index) => {
      const info = resultInfo(value(m,'result'));
      const card = document.createElement('a');
      card.className = 'match-card match-clickable';
      const mid = value(m,'matchId','match_id');
      const detailUrl = '/partidos/' + encodeURIComponent(mid !== null && mid !== undefined && mid !== '' ? String(mid) : 'recent-' + index);
      card.href = detailUrl;
      card.setAttribute('aria-label', 'Ver detalles del partido contra ' + (value(m,'opponentName','opponent') || 'rival'));
      card.innerHTML = `
        <div class="match-result ${info.cls}">${info.short}</div>
        <div class="match-main">
          <strong>${esc(value(m,'opponentName','opponent') || 'Rival no disponible')}</strong>
          <div class="match-meta">${info.label} · ${esc(dateText(value(m,'timestamp','date')))}${(data.match_labels||{})[String(mid)]?.label ? ' · ' + esc((data.match_labels||{})[String(mid)].label) : value(m,'matchType') ? ' · ' + esc(value(m,'matchType')) : ''}</div>
        </div>
        <div class="match-score">
          <strong>${show(value(m,'goals'))} - ${show(value(m,'goalsAgainst','goalsagainst'))}</strong>
          <small>Ver partido →</small>
        </div>
      `;
      matches.append(card);
    });
  }

  const players = $('players');
  players.replaceChildren();
  let members = Array.isArray(data.members) ? data.members.slice() : [];
  const profiles = data.player_profiles || {};
  members = members.filter(p => !profiles[String(value(p,'playerName','name','personaName','persona','player') || '').trim()]?.hidden);
  members.sort((a,b) => n(value(b,'goals')) - n(value(a,'goals')) || n(value(b,'assists')) - n(value(a,'assists')));
  if (!members.length) {
    players.innerHTML = '<tr><td colspan="6" class="empty-state">No hay jugadores disponibles.</td></tr>';
  } else {
    members.forEach(p => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${esc(value(p,'playerName','name') || 'Jugador')}</td>
        <td>${esc(value(p,'position') || '—')}</td>
        <td>${show(value(p,'gamesPlayed','gamesplayed','appearances'))}</td>
        <td>${show(value(p,'goals'))}</td>
        <td>${show(value(p,'assists'))}</td>
        <td>${show(value(p,'averageRating','ratingAve','rating','avgRating'))}</td>
      `;
      players.append(tr);
    });
  }

  renderRankList('top-scorers', members, 'goals', 'goles');
  renderRankList('top-assists', members, 'assists', 'asistencias');
  renderPlayerCards(members, data.player_profiles || {});

}

async function load(){
  try{
    const r = await fetch('/api/club', {cache: 'no-store'});
    if(!r.ok) throw new Error('HTTP ' + r.status);
    render(await r.json());
  } catch(e){
    $('status').textContent = 'No se puede contactar con el servidor';
    $('status-dot').classList.add('offline');
    console.error(e);
  }
}

load();
setInterval(load, 60000);

function playerKey(p) {
  return String(value(p, 'playerName','name','personaName','persona','player') || '').trim();
}
function renderPlayerCards(members, profiles) {
  const root = $('player-cards');
  if (!root) return;
  root.replaceChildren();
  if (!members.length) { root.textContent = 'No hay jugadores disponibles.'; return; }
  members.forEach((p, i) => {
    const key = playerKey(p) || ('Jugador ' + (i+1));
    const custom = profiles[key] || {};
    const display = custom.display_name || key;
    const number = custom.number || '—';
    const pos = custom.position || value(p,'position') || 'PLANTILLA';
    const photo = safeUrl(custom.photo_url);
    const initials = display.split(/\s+/).slice(0,2).map(s => s[0] || '').join('').toUpperCase();
    const card = document.createElement('article');
    card.className = 'player-card';
    const media = document.createElement('div');
    media.className = 'player-card-media';
    if (photo) {
      const img = document.createElement('img'); img.src=photo; img.alt='Foto de ' + display; img.loading='lazy';
      img.onerror = () => {media.textContent=initials;};
      media.append(img);
    } else media.textContent = initials;
    const content = document.createElement('div');
    content.className = 'player-card-content';
    const top = document.createElement('div'); top.className='player-card-top';
    const num=document.createElement('span'); num.className='player-number'; num.textContent='#'+number;
    const position=document.createElement('span'); position.className='player-position'; position.textContent=pos;
    top.append(num,position);
    const name=document.createElement('h3'); name.textContent=display;
    const details=document.createElement('p'); details.textContent=`${show(value(p,'goals'))} goles · ${show(value(p,'assists'))} asistencias`;
    content.append(top,name,details);
    card.append(media,content);
    root.append(card);
  });
}
