"""Registro de herramientas: qué hay, en qué puerto, si está despierta y cuándo se usó por última vez.

Una herramienta es un contenedor de Docker con estas etiquetas:

    wallo.activar=true             obligatoria
    wallo.puerto=8101              puerto del portal por el que se entra (franja 8101-8199)
    wallo.puerto_interno=8000      puerto en el que escucha dentro del contenedor (por defecto 80)
    wallo.nombre=CompElectrix      nombre visible (por defecto, el del contenedor)
    wallo.descripcion=…            texto corto para la página de inicio
    wallo.icono=rayo               icono (ver estatico/app.js) o una letra
    wallo.dormir_tras=15           minutos sin uso antes de apagarla (0 = nunca)
    wallo.salud=/api/salud         ruta que responde cuando está lista (por defecto "/")
    wallo.orden=10                 orden en la página de inicio
    wallo.puerto_publico=8101      puerto con el que se ve desde fuera, si el NAS usa otro
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import aiohttp

from .config import Config
from .docker import Docker, ErrorDocker

log = logging.getLogger("wallo")


@dataclass
class Herramienta:
    id: str
    contenedor: str
    nombre: str
    puerto: int
    puerto_interno: int = 80
    descripcion: str = ""
    icono: str = ""
    dormir_tras: int = 15
    salud: str = "/"
    orden: int = 100
    puerto_publico: int | None = None
    # Estado en tiempo de ejecución
    ejecutando: bool = False
    ip: str | None = None
    lista: bool = False  # responde a peticiones
    ultima_actividad: float = field(default_factory=time.monotonic)
    conexiones: int = 0  # peticiones o websockets abiertos ahora mismo
    error: str | None = None
    version: str | None = None  # la que diga su ruta de salud ({"version": "…"}), si la da
    _despertar: asyncio.Task | None = field(default=None, repr=False)

    @property
    def estado(self) -> str:
        if self.lista:
            return "activa"
        if self._despertar and not self._despertar.done():
            return "despertando"
        if self.ejecutando:
            return "arrancando"
        return "dormida"

    def tocar(self) -> None:
        self.ultima_actividad = time.monotonic()

    def minutos_inactiva(self) -> float:
        return (time.monotonic() - self.ultima_actividad) / 60


def _entero(texto: str | None, defecto: int) -> int:
    try:
        return int(texto) if texto not in (None, "") else defecto
    except ValueError:
        return defecto


def desde_etiquetas(c: dict, cfg: Config) -> Herramienta | None:
    """Crea una herramienta a partir de un contenedor listado por Docker. None si sus etiquetas no son válidas."""
    et = c.get("Labels") or {}
    nombre_cont = (c.get("Names") or ["/?"])[0].lstrip("/")
    puerto = _entero(et.get("wallo.puerto"), 0)
    if not (cfg.puerto_min <= puerto <= cfg.puerto_max):
        log.warning(
            "%s: wallo.puerto=%r fuera de la franja %d-%d; se ignora",
            nombre_cont, et.get("wallo.puerto"), cfg.puerto_min, cfg.puerto_max,
        )  # fmt: skip
        return None
    salud = et.get("wallo.salud") or "/"
    return Herramienta(
        id=c["Id"],
        contenedor=nombre_cont,
        nombre=et.get("wallo.nombre") or nombre_cont,
        puerto=puerto,
        puerto_interno=_entero(et.get("wallo.puerto_interno"), 80),
        descripcion=et.get("wallo.descripcion", ""),
        icono=et.get("wallo.icono", ""),
        dormir_tras=max(0, _entero(et.get("wallo.dormir_tras"), cfg.dormir_por_defecto)),
        salud=salud if salud.startswith("/") else "/" + salud,
        orden=_entero(et.get("wallo.orden"), 100),
        puerto_publico=_entero(et.get("wallo.puerto_publico"), 0) or None,
        ejecutando=c.get("State") == "running",
    )


def ip_del_contenedor(info: dict, red_preferida: str) -> str | None:
    redes = (info.get("NetworkSettings") or {}).get("Networks") or {}
    if red_preferida in redes and redes[red_preferida].get("IPAddress"):
        return redes[red_preferida]["IPAddress"]
    return next((r["IPAddress"] for r in redes.values() if r.get("IPAddress")), None)


class Registro:
    def __init__(self, cfg: Config, docker: Docker):
        self.cfg = cfg
        self.docker = docker
        self.por_puerto: dict[int, Herramienta] = {}
        self.cliente = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3))
        self.al_cambiar_puertos = None  # callback(puertos_nuevos: set[int]) para abrir/cerrar puertos

    async def cerrar(self) -> None:
        await self.cliente.close()

    def lista(self) -> list[Herramienta]:
        return sorted(self.por_puerto.values(), key=lambda h: (h.orden, h.nombre.lower()))

    def por_nombre(self, nombre: str) -> Herramienta | None:
        return next((h for h in self.por_puerto.values() if nombre in (h.contenedor, h.nombre)), None)

    # ------------------------------------------------------------ sincronizar
    async def sincronizar(self) -> None:
        """Lee los contenedores marcados y actualiza el registro conservando el estado de los que ya había."""
        nuevos: dict[int, Herramienta] = {}
        for c in await self.docker.listar():
            h = desde_etiquetas(c, self.cfg)
            if h is None:
                continue
            if h.puerto in nuevos:
                log.warning("Puerto %d repetido (%s y %s); se ignora el segundo", h.puerto, nuevos[h.puerto].contenedor, h.contenedor)
                continue
            previa = self.por_puerto.get(h.puerto)
            if previa and previa.id == h.id:
                h.ultima_actividad, h.conexiones, h._despertar = previa.ultima_actividad, previa.conexiones, previa._despertar
                h.lista, h.ip, h.version = previa.lista and h.ejecutando, previa.ip, previa.version
            if h.ejecutando and not h.lista:
                await self._comprobar_lista(h)
            nuevos[h.puerto] = h
        cambiaron = set(nuevos) != set(self.por_puerto)
        self.por_puerto = nuevos
        if cambiaron and self.al_cambiar_puertos:
            await self.al_cambiar_puertos(set(nuevos))

    async def _comprobar_lista(self, h: Herramienta) -> bool:
        try:
            h.ip = ip_del_contenedor(await self.docker.inspeccionar(h.id), self.cfg.red_preferida)
        except ErrorDocker as e:
            h.error = str(e)
            return False
        if not h.ip:
            return False
        try:
            async with self.cliente.get(f"http://{h.ip}:{h.puerto_interno}{h.salud}", allow_redirects=False) as r:
                h.lista = r.status < 500
                if h.lista and "json" in r.headers.get("Content-Type", ""):
                    try:
                        v = (await r.json()).get("version")
                        h.version = str(v)[:20] if v else h.version
                    except (ValueError, AttributeError, aiohttp.ContentTypeError):
                        pass
        except (aiohttp.ClientError, asyncio.TimeoutError):
            h.lista = False
        return h.lista

    # -------------------------------------------------------- despertar/dormir
    def despertar(self, h: Herramienta) -> asyncio.Task:
        """Arranca la herramienta si hace falta (una sola vez aunque lleguen muchas peticiones)."""
        if h._despertar is None or h._despertar.done():
            h._despertar = asyncio.create_task(self._despertar_y_esperar(h))
        return h._despertar

    async def _despertar_y_esperar(self, h: Herramienta) -> bool:
        h.error = None
        h.tocar()
        try:
            if not h.ejecutando:
                log.info("Despertando %s", h.nombre)
                await self.docker.arrancar(h.id)
                h.ejecutando = True
            limite = time.monotonic() + self.cfg.espera_maxima
            while time.monotonic() < limite:
                if await self._comprobar_lista(h):
                    log.info("%s lista", h.nombre)
                    return True
                await asyncio.sleep(0.5)
            h.error = f"No respondió en {self.cfg.espera_maxima} s"
        except ErrorDocker as e:
            h.error = str(e)
            log.warning("No se pudo despertar %s: %s", h.nombre, e)
        return False

    async def esperar_lista(self, h: Herramienta) -> bool:
        if h.lista:
            return True
        try:
            return await asyncio.wait_for(asyncio.shield(self.despertar(h)), self.cfg.espera_maxima + 5)
        except asyncio.TimeoutError:
            return False

    async def dormir(self, h: Herramienta, motivo: str = "") -> None:
        log.info("Durmiendo %s%s", h.nombre, f" ({motivo})" if motivo else "")
        h.lista = False
        try:
            await self.docker.parar(h.id)
            h.ejecutando = False
            h.ip = None
        except ErrorDocker as e:
            h.error = str(e)

    async def revisar_inactivas(self) -> None:
        for h in list(self.por_puerto.values()):
            if (
                h.ejecutando
                and h.dormir_tras > 0
                and h.conexiones == 0
                and not (h._despertar and not h._despertar.done())
                and h.minutos_inactiva() >= h.dormir_tras
            ):
                await self.dormir(h, f"{h.dormir_tras} min sin uso")

    # ------------------------------------------------------------- eventos
    def aplicar_evento(self, ev: dict) -> bool:
        """Actualiza el estado con un evento de Docker. Devuelve True si hay que volver a sincronizar."""
        accion = ev.get("Action") or ev.get("status") or ""
        id_ = ev.get("id") or (ev.get("Actor") or {}).get("ID")
        h = next((x for x in self.por_puerto.values() if x.id == id_), None)
        if accion in ("create", "destroy", "rename", "update") or h is None:
            return accion in ("create", "destroy", "rename", "update", "start")
        if accion == "start":
            h.ejecutando = True
            h.tocar()  # si alguien la arranca a mano, cuenta como uso
        elif accion in ("die", "stop", "kill", "oom"):
            h.ejecutando = h.lista = False
            h.ip = None
        return False
