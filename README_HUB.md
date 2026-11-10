# LOS INTOCABLES HUB · EA Sports FC 27

Primera versión funcional basada en la web anterior. Conserva las rutas, los estilos, la plantilla, las fotos, el acceso al panel, la consulta de FC 27 y las fichas clicables de partido. Se añaden calendario, ligas, fichajes, etiquetado de partidos y sincronización con el bot Discord.

## Qué se puede utilizar hoy

- **Inicio `/`**: resumen, partidos recientes clicables, rankings, fotos y fichas de la plantilla; novedades de ligas y calendario.
- **Partido `/partidos/<id>`**: pestañas de resumen, estadísticas, jugadores y alineaciones **solo cuando la API devuelve esos datos**; permite consultar partidos archivados con ID estable.
- **Ligas `/competiciones`**: VPG Bronze Zero, AFJ 4ª División y VPG 5ª División; horarios habituales y enlaces editables; calendario con partidos **confirmados manualmente**.
- **Fichajes `/fichajes`**: formulario sin correo; envía candidaturas a la base de datos. El administrador cambia el estado (pendiente, pruebas, aceptado o rechazado).
- **Panel `/admin`**: acceso restringido, personalización, cambio de fotos por URL/archivo, ocultación de jugadores, calendario CRUD, ligas editables, etiquetas de partidos, candidaturas.
- **Bot FC27**: conexión opcional con token `HUB_SYNC_TOKEN` para enviar al HUB los mismos datos que recibe el bot. El bot continúa publicando en Discord.
- **API**: `/api/club`, `/api/hub`, `/api/partidos`, `/api/partidos/<id>`, `/api/health` y endpoint protegido de ingesta.

Las estadísticas provienen de la biblioteca comunitaria `fc-clubs-api==0.3.0` o de los snapshots del bot; **no hay datos simulados en producción**. La API puede no ofrecer tiros, posesión, alineaciones o datos por jugador para todos los partidos. Las ligas/amistosos no se clasifican automáticamente cuando la fuente no aporta una identificación fiable.

## Ejecutar la web en Windows (recomendado Python 3.11)

1. Descomprime este ZIP. Abre PowerShell en la carpeta `LOS_INTOCABLES_HUB` (donde está `main.py`).
2. Ejecuta:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

3. Edita **`.env`** y sustituye los campos de ejemplo por secretos aleatorios reales. Usa una contraseña de al menos 12 caracteres, un `SESSION_SECRET` de al menos 24 y un `HUB_SYNC_TOKEN` de al menos 24. Los tres deben ser distintos. Ejemplo para generar cada uno:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(40))"
```

4. Inicia la web:

```powershell
uvicorn main:app --reload
```

5. Abre `http://127.0.0.1:8000/` y luego `http://127.0.0.1:8000/login` para entrar como admin.

> Si quieres que la web dependa **solo** del bot, usa `DATA_SOURCE=bot` en `.env`. De lo contrario `DATA_SOURCE=auto` consulta a FC 27 por su cuenta y puede recibir actualizaciones adicionales del bot.

## Publicar en GitHub + Render

La web ya tiene el archivo `render.yaml` y está preparada para el comando de Render:

```
uvicorn main:app --host 0.0.0.0 --port $PORT
```

1. Haz una copia del repositorio que actualmente sirve la web. Sube los **archivos extraídos de la raíz del HUB** a la raíz de tu repositorio. No subas `.env`, `site.db`, ficheros de caché ni credenciales.
2. En Render, revisa qué repositorio y rama están conectados al servicio `los-intocables.onrender.com`. Actualiza **ese servicio existente** para no cambiar la URL.
3. Configura en Render `ADMIN_USER`, `ADMIN_PASSWORD`, `SESSION_SECRET`, `HUB_SYNC_TOKEN`, `DATA_SOURCE` (auto o bot), `CLUB_NAME` y `COOKIE_SECURE=true`. `render.yaml` define los valores no sensibles; los secretos van en Environment de Render.
4. Deploy. Abre `/api/health` para comprobar si llegan estadísticas, después prueba el panel, fichajes y calendario.

**Aviso sobre persistencia en Render:** las instancias sin disco persistente pueden perder el archivo SQLite (`site.db`) al reiniciarse o desplegarse. Para producción **necesitas almacenamiento persistente** (disco compatible con tu plan o migración a una base de datos gestionada). No confíes en SQLite sobre almacenamiento efímero para fotos, calendario, solicitudes o etiquetados.

## Conectar vuestro bot Discord sin perder sus datos

La carpeta `bot_fc27/` contiene una **versión modificada del bot base** con sincronización del HUB. Si en tu PC el bot tiene cambios personalizados hechos después, **no sustituyas su `app.py` sin compararlos antes**; incorpora solo los cambios de `sync_to_hub()` y la llamada posterior a `refresh_data()`.

En el archivo **`.env` del bot, que solo debe estar en tu PC**, agrega:

```
HUB_URL=https://los-intocables.onrender.com
HUB_SYNC_TOKEN=EL_MISMO_TOKEN_DE_RENDER
```

Conserva `DISCORD_TOKEN`, `DISCORD_CHANNEL_ID`, `CLUB_NAME` y el resto de tus valores existentes. Ejecuta el bot como lo hacías normalmente. Si el envío al HUB falla, el bot registra el error y continúa funcionando con Discord.

El endpoint `/api/integrations/bot/snapshot` rechaza envíos sin el token compartido. **Nunca incluyas tokens en URLs, GitHub o capturas de pantalla.**

## Seguridad y limitaciones

- Si tu repositorio público contiene un archivo `.env`, quítalo del repositorio y del historial cuando corresponda y **rota inmediatamente todos los tokens y contraseñas que pudiera contener**. El ZIP de esta entrega **no** incluye un `.env` real.
- Las cuentas públicas de jugadores no están implementadas en esta primera versión: solo hay una sesión de administrador. Las candidaturas son públicas pero se gestionan en privado.
- No hay clasificación automática verificada de las ligas; puedes poner el enlace oficial en el panel, pero no extraemos clasificaciones de webs externas arbitrarias. La sincronización de clasificación será una integración aparte con una fuente compatible.
- Los envíos de fichajes incluyen limitación básica por IP en memoria. Para una web muy pública conviene añadir protección antispam persistente y CSRF adicional.
- Los identificadores de partidos **solo son archivables** cuando la API trae un `matchId`/`match_id` estable. Los índices `recent-N` sirven solo para consultas recientes y pueden cambiar con el tiempo.

## Pruebas

```bash
pip install pytest httpx
DATA_SOURCE=bot pytest -q tests/test_hub.py
```

Las pruebas cubren páginas, admin, calendarios, competiciones, solicitudes, clasificación manual, sincronización bot y archivo de un partido.
