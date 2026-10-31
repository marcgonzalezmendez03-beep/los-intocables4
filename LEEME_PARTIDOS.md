# Fichas de partidos — Los Intocables

- Los partidos con ID son clicables en la página principal.
- Cada partido abre `/partidos/<ID>` con Resumen, Alineaciones, Estadísticas y Jugadores.
- `/api/partidos/<ID>` entrega los datos reales que devuelve FC27 API.
- Se consultan los 30 partidos más recientes en cada actualización y se archivan por ID en SQLite.
- La API usada actualmente (`get_club_matches`) puede no incluir alineaciones o métricas individuales. En ese caso, la página muestra «No disponible» y **no inventa datos**. Para una alineación táctica completa se necesita una fuente adicional de estadísticas por jugador y posición de ese partido.
- El historial SQLite puede perderse en Render Free por su disco efímero.
- Subir el CONTENIDO de este proyecto a GitHub (no el ZIP). No subir `.env`, contraseñas ni `site.db`.
- Start Command Render: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
