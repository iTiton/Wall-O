# Wall-O

Muro de inicio para aplicaciones. 

Portal para tus herramientas caseras en Docker. Las **duerme cuando no las usas** (0 MB de memoria) y las
**despierta al entrar**, en unos segundos. Tiene una página de inicio, adaptada al móvil y al ordenador,
con todas tus herramientas y su estado.

```
Navegador ──► Wall-O (siempre encendido, ~30 MB)
                ├─ :8100  Página de inicio
                ├─ :8101  CompElectrix   ← dormida hasta que entras
                ├─ :8102  otra herramienta
                └─ …      (franja 8101-8199, un puerto por herramienta)
```

- **Consumo mínimo**: solo Wall-O está siempre encendido (unos 30 MB). Cada herramienta se apaga tras unos
  minutos sin uso (15 por defecto) y vuelve a arrancar al abrirla.
- **Sin configuración central**: una herramienta aparece sola en el portal en cuanto su contenedor tiene
  las etiquetas `wallo.*`.
- **Seguro por diseño**: las herramientas no publican puertos propios y solo se llega a ellas a través del
  portal. Wall-O solo enciende y apaga los contenedores marcados con `wallo.activar=true`.
- Tema claro, oscuro o automático. Se puede añadir a la pantalla de inicio del móvil como si fuera una app.

## Instalación (Raspberry Pi o cualquier equipo con Docker)

Necesitas Docker instalado. Si aún no lo tienes, en la Raspberry:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER      # después cierra la sesión y vuelve a entrar
```

Descarga Wall-O y arráncalo:

```bash
git clone https://github.com/iTiton/Wall-O.git
cd Wall-O
docker compose up -d --build
```

Abre `http://raspberrypi.local:8100` (o `http://IP-DE-LA-RASPBERRY:8100`). Al principio estará vacío.

> Wall-O se instala **antes** que las herramientas: al arrancar crea la red de Docker `wallo` que ellas usan.

¿Usas **Portainer**? Sigue [docs/portainer.md](docs/portainer.md): instala Wall-O y CompElectrix desde su interfaz.

### Actualizar

```bash
cd Wall-O
git pull
docker compose up -d --build
docker image prune -f      # borra la versión anterior de la imagen
```

## Añadir una herramienta

Basta con poner etiquetas al contenedor de la herramienta, quitarle sus puertos y conectarlo a la red `wallo`.
Ejemplo con un `docker-compose.yml`:

```yaml
services:
  mi-herramienta:
    image: …
    restart: unless-stopped
    networks: [wallo]                 # sin "ports:": solo se entra por el portal
    labels:
      wallo.activar: "true"
      wallo.puerto: "8102"            # puerto por el que se entra (8101-8199, uno distinto por herramienta)
      wallo.puerto_interno: "80"      # puerto en el que escucha dentro del contenedor
      wallo.nombre: Mi herramienta
      wallo.descripcion: Para qué sirve
      wallo.icono: herramienta        # rayo, casa, grafica, nube, archivo, herramienta, camara,
                                      # musica, libro, servidor, euro, calendario (o una letra)
      wallo.salud: /                  # ruta que responde cuando ya está lista
      wallo.dormir_tras: "15"         # minutos sin uso antes de dormirla (0 = nunca)
      wallo.orden: "20"               # orden en la página de inicio

networks:
  wallo:
    external: true
```

Después, `docker compose up -d` en la carpeta de la herramienta: aparecerá sola en la página de inicio.

**CompElectrix** ya trae su archivo preparado (`docker-compose.wallo.yml`). Mira la sección «Con el portal
Wall-O» de su README.

Si vas a programar una herramienta propia, lee [docs/crear-herramientas.md](docs/crear-herramientas.md).

## Acceso desde fuera de casa, con HTTPS (Synology)

Wall-O funciona dentro de tu red. Para entrar desde fuera con candado HTTPS, a través de la VPN y con el
certificado de un NAS Synology, sigue [docs/synology.md](docs/synology.md).

## Ajustes

Todos son opcionales y se ponen en `environment:` dentro de `docker-compose.yml`:

| Variable | Por defecto | Para qué |
|---|---|---|
| `WALLO_DORMIR_TRAS` | `15` | Minutos sin uso antes de dormir (si la herramienta no indica otro) |
| `WALLO_PUERTO` | `8100` | Puerto de la página de inicio |
| `WALLO_PUERTO_MIN` / `WALLO_PUERTO_MAX` | `8101` / `8199` | Franja de puertos para herramientas |
| `WALLO_ESPERA_MAXIMA` | `90` | Segundos esperando a que una herramienta arranque |
| `WALLO_RED` | `wallo` | Red de Docker de las herramientas |

## Recursos

| | Memoria | CPU en reposo |
|---|---|---|
| Wall-O | ~30 MB | ~0 % |
| Cada herramienta dormida | 0 MB | 0 % |

Wall-O no consulta nada periódicamente: se entera de los cambios por los avisos de Docker y solo revisa
la inactividad cada 30 segundos (una operación de microsegundos).

## Seguridad

- Wall-O usa el socket de Docker para encender y apagar contenedores. Ese acceso equivale a ser administrador
  de la máquina, así que el código **solo actúa sobre contenedores con `wallo.activar=true`** y lo comprueba
  antes de cada acción. Su contenedor es de solo lectura y no puede ganar privilegios.
- No tiene usuarios ni contraseñas: está pensado para usarse **dentro de casa o por VPN**, nunca abierto a internet.
  La guía de Synology incluye una prueba para comprobarlo.

## Desarrollo

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest pytest-aiohttp
.venv/bin/python -m pytest -q
.venv/bin/python -m wallo          # necesita acceso a /var/run/docker.sock
```

Estructura:

- `wallo/herramientas.py`: registro, etiquetas, despertar y dormir.
- `wallo/proxy.py`: proxy HTTP y WebSocket.
- `wallo/inicio.py` y `wallo/estatico/`: página de inicio (HTML, CSS y JS sin compilar).
- `wallo/docker.py`: cliente mínimo de la API de Docker.

## Licencia

[GPL-3.0-or-later](LICENSE).
