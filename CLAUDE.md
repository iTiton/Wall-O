# Wall-O — contexto para Claude

Portal casero (Python + aiohttp) que da acceso a herramientas en Docker y las duerme cuando no se usan.
Se ejecuta en una Raspberry Pi 4 (4 GB) junto a las herramientas (la primera es CompElectrix, en el repositorio
iTiton/CompElectrix). Licencia GPL-3.0-or-later. Todo en español: interfaz, código y documentación.

## Cómo trabajar con la persona usuaria

- Antes de escribir algo que firmará, preguntar qué quiere decir y qué sabe ya.
- Al revisar algo suyo, señalar los fallos sin reescribirlos. Al pulir, no cambiar tesis, ejemplos ni añadir datos.
- Si pregunta algo que le conviene aprender, hacer preguntas antes de dar la respuesta.
- Sabe informática básica: explicar los pasos de despliegue con detalle y sin jerga.

## Decisiones

- **Un puerto por herramienta**: 8100 es la portada y las herramientas usan la franja 8101-8199. La persona usuaria
  lo eligió para encajar con el proxy inverso de su NAS Synology, que reparte por puerto y no por ruta.
- `network_mode: host` en Wall-O: abre los puertos según aparecen las herramientas, sin un docker-proxy por puerto,
  y llega a las herramientas por su IP en la red `wallo`, que Wall-O crea al arrancar.
- Las herramientas no publican puertos. El descubrimiento es por etiquetas `wallo.*`, y Wall-O solo actúa sobre
  contenedores con `wallo.activar=true` (lo vuelve a comprobar antes de cada acción).
- Sin consultas periódicas a Docker: se usan sus eventos. Solo hay una revisión de inactividad cada 30 s.
- Prioridad: poca memoria (~30 MB en reposo). Solo depende de aiohttp. La interfaz es HTML, CSS y JS sin compilar.
- La pantalla de espera responde 200, no 503, porque el proxy del NAS podría sustituir las páginas de error.
- HTTPS y VPN: los pone el NAS Synology (ver docs/synology.md). No escribir su dominio real en el repositorio.
  Pendiente: confirmar el tipo de VPN (para el DNS) y que el router no redirige la franja 8100-8199.

## Versiones y ramas

- `main` es la versión estable (la que se instala). La 1.00 se fusionó el 15/11/2026.
- La siguiente versión (1.01, 1.02…) se trabaja en una rama aparte. Cuando está madura, se crea una pull request
  hacia `main` y la fusiona Claude cuando la persona usuaria lo pide. Después, la siguiente versión empieza en otra rama.
- No subir nada directamente a `main`.
- **Número de versión**: `wallo/__init__.py` (`__version__`). Se pone el de la versión en curso al empezarla y se
  comprueba antes de fusionar. La portada muestra la de Wall-O y la de cada herramienta que la dé en su ruta de salud.

## Comprobaciones

```bash
.venv/bin/python -m pytest -q
```

Después, probar con Docker real: Wall-O en contenedor, CompElectrix con `docker-compose.wallo.yml`, el ciclo
dormir/despertar en el navegador y la portada en ancho de móvil y de ordenador, con tema claro y oscuro.
