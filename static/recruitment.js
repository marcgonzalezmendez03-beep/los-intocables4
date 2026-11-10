const form=document.getElementById('apply-form'); const feedback=document.getElementById('apply-feedback');
form.addEventListener('submit',async e=>{
 e.preventDefault(); const btn=form.querySelector('button[type=submit]'); btn.disabled=true;
 feedback.textContent='Enviando…';
 try {
  const r=await fetch('/api/fichajes/solicitud',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(form)))});
  const data=await r.json(); if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'No se pudo enviar.');
  feedback.textContent='✓ Solicitud enviada. El administrador podrá revisarla en el panel.';form.reset();
 }catch(err){feedback.textContent=err.message||'Error de conexión.';}
 finally{btn.disabled=false;}
});
