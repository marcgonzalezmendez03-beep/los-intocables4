const form = document.getElementById('settings');
const message = document.getElementById('message');

async function load(){
  const r = await fetch('/api/club');
  const c = (await r.json()).customization || {};
  for (const k of ['title','subtitle','crest_url','announcement']) form.elements[k].value = c[k] || '';
}

load();

form.addEventListener('submit', async e => {
  e.preventDefault();
  message.textContent = 'Guardando cambios…';
  const data = Object.fromEntries(new FormData(form));
  const r = await fetch('/api/admin/settings', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  message.textContent = r.ok ? 'Cambios guardados correctamente.' : ((await r.json()).detail || 'No se pudo guardar.');
});

document.getElementById('refresh').onclick = async () => {
  message.textContent = 'Consultando FC27…';
  const r = await fetch('/api/admin/refresh', {method: 'POST'});
  const d = await r.json();
  message.textContent = d.ok ? 'Datos actualizados correctamente.' : 'No se pudo actualizar: ' + d.error;
};

document.getElementById('logout').onclick = async () => {
  await fetch('/api/logout', {method: 'POST'});
  location.href = '/';
};


async function loadProfiles(){
  const root = document.getElementById('profile-editor');
  if (!root) return;
  try {
    const r = await fetch('/api/club', {cache:'no-store'});
    if (!r.ok) throw new Error('Error al obtener plantilla');
    const data = await r.json();
    root.replaceChildren();
    const members = Array.isArray(data.members) ? data.members : [];
    if (!members.length) {root.textContent='Sin jugadores disponibles.'; return;}
    members.forEach(p => {
      const key=String(p.playerName || p.name || p.personaName || p.persona || p.player || '').trim();
      if (!key) return;
      const c=(data.player_profiles || {})[key] || {};
      const form=document.createElement('form'); form.className='player-edit-card';
      const heading=document.createElement('h3'); heading.textContent=key; form.append(heading);
      const fields=[['display_name','Nombre visible',c.display_name||''],['number','Dorsal',c.number||''],['position','Posición',c.position||''],['photo_url','URL de foto (https://...)',c.photo_url||'']];
      const grid=document.createElement('div');grid.className='profile-edit-grid';
      fields.forEach(([name,label,value])=>{
        const wrapper=document.createElement('label'); wrapper.textContent=label;
        const input=document.createElement('input');input.name=name;input.value=value; input.maxLength=name==='number'?3:name==='position'?20:name==='display_name'?80:1000;
        wrapper.append(input);grid.append(wrapper);
      });
      form.append(grid);
      const actions=document.createElement('div');actions.className='form-actions';
      const button=document.createElement('button');button.className='primary-button';button.type='submit';button.textContent='Guardar ficha';
      const info=document.createElement('span');info.className='note';
      actions.append(button,info);form.append(actions);
      form.addEventListener('submit', async e=>{
        e.preventDefault(); button.disabled=true;info.textContent='Guardando…';
        const values=Object.fromEntries(new FormData(form));
        try {
          const response=await fetch('/api/admin/player',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({player_key:key,...values})});
          const result=await response.json();
          info.textContent=response.ok?'Ficha guardada.':(result.detail || 'No se pudo guardar.');
        } catch { info.textContent='Error de conexión.'; }
        button.disabled=false;
      });
      root.append(form);
    });
  } catch {root.textContent='No se ha podido cargar la plantilla.';}
}
loadProfiles();
