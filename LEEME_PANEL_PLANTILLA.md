# Los Intocables — Panel de plantilla

En `/admin`, cada jugador tiene:
- Casilla **Ocultar este jugador**: desaparece de plantilla, goleadores y asistencias públicas, pero conserva sus estadísticas reales.
- **URL de foto**: imagen alojada en una dirección pública HTTP/HTTPS.
- **Subir foto desde ordenador**: JPG, PNG, WEBP o GIF, hasta 3 MB. Se almacena en la base de datos SQLite del servidor.
- **Guardar ficha**: aplica los cambios.

No incluyas `.env` ni `site.db` en GitHub.

**Importante para Render gratuito:** el disco es efímero. Si Render reinicia o redepliega el servicio, los cambios del panel y las fotos subidas pueden desaparecer. Para conservarlos de forma permanente se necesita una base de datos/almacenamiento persistente externo o un disco persistente de pago.
