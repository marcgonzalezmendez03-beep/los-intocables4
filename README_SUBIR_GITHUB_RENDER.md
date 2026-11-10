# Los Intocables 4 — archivos listos para GitHub + Render

## Subir a GitHub

Este ZIP contiene los archivos en **la raíz**, junto a `main.py`, `render.yaml` y `requirements.txt` (sin carpeta exterior). No es necesario abrir terminal ni ejecutar instaladores.

1. Antes de nada, en tu repositorio descarga un ZIP de seguridad: **Code → Download ZIP**. Guarda también la BD de Render si tienes un disco persistente.
2. Descomprime **este** ZIP y sube sus archivos y carpetas a la raíz de `marcgonzalezmendez03-beep/los-intocables4` en GitHub. Conserva sus rutas (`static`, `templates`, etc.).
3. Confirma los cambios (Commit changes) en la rama usada por Render.
4. Si Render tiene auto-deploy, se publicará con el commit; si no, entra en Render y usa **Manual Deploy → Deploy latest commit**.
5. Comprueba `/api/health`, `/api/explorador/estado`, `/api/ligas/estado` y `/api/ligas/competiciones` en el dominio de Render.

## Importante sobre la versión de `main.py`

**No se ha podido descargar el estado actual de `los-intocables4` de GitHub.**
Este ZIP COMPLETO se ha construido sobre la **última copia disponible en esta conversación** del HUB de Los Intocables (6-nov-2026). Se han incluido los módulos V4 y la integración en `main.py` para que Render arranque sin ejecutar `instalar_todo.py`.
**Si editaste `main.py`, `templates/index.html` o los otros archivos en GitHub posteriormente, subir este ZIP podría reemplazar esas modificaciones.** Guarda copia y compara primero.

## Las ligas

- VPG 5C (ID interno `vpg-quinta`), [referencia EAFCStats 294](https://eafcstats.es/competitions/294).
- VPG Zero Bronze (`vpg-bronze-zero`), [referencia EAFCStats 301](https://eafcstats.es/competitions/301).
- AFJ 4A (`afj-cuarta`). **No uses el enlace AFJ 5A** como fuente de 4A.

**ATENCIÓN:** ninguna página pública citada se ha verificado como un feed de calendario exportable. `calendarios_fuentes.json` tiene URL vacías de forma intencional. La clasificación automática ya está lista para leer los partidos de tu panel `fixtures` y, si más adelante conectas feeds CSV/JSON/ICS autorizados, los actualizará automáticamente. No afirmes que los partidos estarán clasificados sin esos datos.

## Qué funciona

- Resumen y estadísticas generales de club / jugadores.
- Historial con filtros por ligas y botones de partido.
- Página de detalle `/partidos/ID` con datos de `get_club_matches(..., output="raw")` **solo cuando EA entrega datos para ese ID**.
- Administración del HUB, panel de fichajes y otras rutas del proyecto base.
- Rutas para consultar sincronización y estado de feeds, y recálculo por administrador.

## Render y privacidad

- No se ha añadido ningún token ni contraseña. Configura `ADMIN_USER`, `ADMIN_PASSWORD`, `SESSION_SECRET` y otras variables en Render.
- Si el servicio está configurado manualmente desde Render, confirma que el Start Command sea `uvicorn main:app --host 0.0.0.0 --port $PORT` y el Build Command sea `pip install -r requirements.txt`. Un `render.yaml` en GitHub no cambia automáticamente los ajustes de un servicio existente si no fue creado como Blueprint.
- Guarda `site.db` en un disco persistente y configura `DATABASE_PATH` para no perder asignaciones, fotos ni datos históricos al redeploy.
- El backend consulta EA FC27; el historial detallado futuro depende de la API de EA y del servidor ejecutándose.

## Pruebas locales

`python -m pytest -q tests/test_auto_ligas.py tests/test_explorer.py tests/test_hub.py`

El ZIP no incluye `.env`, `site.db`, tokens ni contraseñas.
