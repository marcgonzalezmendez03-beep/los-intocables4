# Novedades HUB 1.0

- Web anterior conservada y expandida (sin reinventar el stack FastAPI/Jinja/SQLite/JS).
- Nuevas páginas públicas `/competiciones` y `/fichajes`.
- Ligas VPG/AFJ editables con horarios habituales inicialmente registrados.
- Próximos partidos reales introducidos por administrador con crear, editar, borrar.
- Solicitudes de jugadores guardadas en SQLite, visibles y gestionables solo por el administrador.
- Etiquetas de liga/amistoso para partidos de FC 27 sin afirmar una clasificación no provista por la fuente.
- Sincronización opcional con bot mediante POST autenticado con token largo.
- Enlaces de partido en avisos del bot Discord.
- Archivo de partidos, estado de conexión y origen del snapshot.
- Se ha corregido un error de alineaciones que pasaba la lista de jugadores como nombre del equipo.
- `.env.example` seguro sin tokens reales, guía de configuración en Windows y Render.
