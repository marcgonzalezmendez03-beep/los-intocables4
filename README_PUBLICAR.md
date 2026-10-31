# Los Intocables · GitHub + Render gratis

Esta carpeta es el **proyecto completo**, con portada V5 y API general FC27 restaurada (sin filtro de amistosos).

## 1. GitHub
1. Crea un repositorio nuevo en github.com/new (preferentemente **Private**).
2. En el repositorio vacío, pulsa **Add file > Upload files**.
3. **Extrae el ZIP antes**. Sube los archivos y carpetas que hay dentro de esta carpeta, **no** la carpeta contenedora ni el ZIP. `main.py` y `requirements.txt` deben quedar en la raíz.
4. Verifica que no hayas subido `.env`, `site.db`, `.venv`, contraseñas ni copias de seguridad.
5. Pulsa **Commit changes**.

## 2. Render
1. En dashboard.render.com, **New > Web Service**, conecta GitHub y selecciona el repositorio.
2. Elige **Free**, región cercana y rama main. Si Render detecta render.yaml, puedes optar por **New > Blueprint**; para principiantes es más fácil Web Service manual.
3. **Build Command**: `pip install -r requirements.txt`
4. **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. **Environment** (en Render, no GitHub): `CLUB_NAME=Los Intocables`, `REFRESH_MINUTES=5`, `COOKIE_SECURE=true`, `ADMIN_USER=<tu_usuario>`, `ADMIN_PASSWORD=<contraseña larga nueva>`, `SESSION_SECRET=<secreto aleatorio largo>` (puedes generarlo en Python: `python -c "import secrets; print(secrets.token_urlsafe(48))"`).
6. Deploy y comprueba la URL HTTPS, `/api/health` y `/login`.

## 3. Limitación muy importante
Render Free detiene el servicio tras 15 minutos sin visitas y pierde los cambios escritos en el disco local al dormir, reiniciarse o desplegarse. Por tanto **SQLite (`site.db`) no es persistente**: los cambios del panel admin pueden desaparecer. Los datos de FC27 se vuelven a descargar de la API al arrancar. Para conservar ajustes a largo plazo hay que migrar el almacenamiento a un servicio externo persistente (p. ej. PostgreSQL); no basta con subir site.db.

## 4. Seguridad
- Nunca publiques tu `.env`, `site.db`, ni contraseñas en GitHub. `.gitignore` protege operaciones Git normales, pero **la subida web manual de GitHub no lo aplica automáticamente**. Comprueba uno por uno los archivos seleccionados.
- No reutilices la contraseña admin local si ya la has compartido; usa una nueva.
- Este despliegue es una prueba pública; el panel tiene login pero no incluye protección avanzada contra intentos repetidos.
- Para uso público continuado conviene añadir persistencia, rate limiting y monitorización.
