# FC 27 Clubs — web + Discord

Starter project para consultar datos públicos de Pro Clubs con la biblioteca comunitaria `fc-clubs-api`, mostrar un dashboard web y publicar avisos de partidos nuevos en Discord.

## Requisitos
- Windows y Python 3.9+.
- Nombre exacto del club.
- Opcional: aplicación/bot creado en el Discord Developer Portal y un canal donde pueda enviar mensajes.

## Instalación rápida (Windows)
1. Descomprime el ZIP en una carpeta.
2. Ejecuta `start_windows.bat`. Instalará dependencias y creará `.env` si no existe.
3. Abre `.env` con el Bloc de notas y cambia `CLUB_NAME=Los Intocables` por el nombre exacto del club.
4. Para Discord, añade `DISCORD_TOKEN` y `DISCORD_CHANNEL_ID`. Nunca compartas el token ni lo publiques.
5. Ejecuta en esa carpeta:
   ```bat
   .venv\Scripts\activate
   python app.py
   ```
6. Abre `http://127.0.0.1:8000`.

## Configurar Discord
1. Crea una aplicación y un bot en https://discord.com/developers/applications
2. Copia el token del bot a `DISCORD_TOKEN` en `.env`.
3. Invita el bot a tu servidor con permiso para ver el canal y enviar mensajes / embeds.
4. Copia el ID del canal de avisos a `DISCORD_CHANNEL_ID` (activa el modo desarrollador de Discord para copiarlo).

## Qué hace
- Obtiene detalles, estadísticas generales, plantilla y hasta 10 partidos recientes.
- Guarda la última respuesta en `data.json`.
- Reintenta con la siguiente actualización si hay un error.
- El dashboard lee la caché y se actualiza al reiniciar/refrescar el navegador.
- Revisa cada 5 minutos y publica un aviso si cambia el ID del partido más reciente.

## Importante
- Esta es una plantilla inicial; no se ha podido probar contra tu club concreto desde aquí.
- La API comunitaria no es oficial y sus endpoints pueden cambiar o bloquear solicitudes.
- La consulta de partidos está limitada por EA a 10 resultados y no ofrece paginación en la API descrita por el proyecto.
- Si el bot detecta un partido, publica un aviso genérico con su ID; el formato real de las respuestas puede variar y conviene ajustarlo con una muestra real.
- Para mantenerlo activo con el PC apagado, habrá que desplegarlo en un servidor. No incluyas tu token de Discord en capturas ni lo subas a GitHub.
