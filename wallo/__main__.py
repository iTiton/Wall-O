"""Arranque: `python -m wallo`."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal

from aiohttp import web

from .config import Config
from .docker import Docker, ErrorDocker
from .herramientas import Registro
from .inicio import crear_app_inicio
from .proxy import crear_app_proxy

log = logging.getLogger("wallo")


class Portal:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.docker = Docker(cfg.socket_docker)
        self.registro = Registro(cfg, self.docker)
        self.registro.al_cambiar_puertos = self.abrir_puertos
        self.proxy = web.AppRunner(crear_app_proxy(self.registro), access_log=None)
        self.inicio = web.AppRunner(crear_app_inicio(self.registro), access_log=None)
        self.sitios: dict[int, web.TCPSite] = {}

    async def abrir_puertos(self, puertos: set[int]) -> None:
        """Escucha en los puertos de las herramientas actuales y deja de hacerlo en los que ya no existen."""
        for p in set(self.sitios) - puertos:
            await self.sitios.pop(p).stop()
            log.info("Puerto %d cerrado", p)
        for p in sorted(puertos - set(self.sitios)):
            sitio = web.TCPSite(self.proxy, "0.0.0.0", p, reuse_address=True)
            try:
                await sitio.start()
                self.sitios[p] = sitio
                h = self.registro.por_puerto[p]
                log.info("Puerto %d → %s (%s)", p, h.nombre, h.contenedor)
            except OSError as e:
                log.error("No se puede usar el puerto %d: %s", p, e)

    async def escuchar_eventos(self) -> None:
        """Mantiene el registro al día con los eventos de Docker (sin consultar periódicamente)."""
        while True:
            try:
                if await self.docker.asegurar_red(self.cfg.red_preferida):
                    log.info("Red de Docker «%s» creada para las herramientas", self.cfg.red_preferida)
                await self.registro.sincronizar()
                async for ev in self.docker.eventos():
                    if self.registro.aplicar_evento(ev):
                        await self.registro.sincronizar()
            except ErrorDocker as e:
                log.warning("%s. Reintentando en 10 s…", e)
            await asyncio.sleep(10)

    async def revisar_inactividad(self) -> None:
        while True:
            await asyncio.sleep(self.cfg.intervalo_revision)
            try:
                await self.registro.revisar_inactivas()
            except Exception:  # noqa: BLE001 - que una herramienta no tumbe el portal
                log.exception("Error revisando inactividad")

    async def ejecutar(self) -> None:
        await self.proxy.setup()
        await self.inicio.setup()
        await web.TCPSite(self.inicio, "0.0.0.0", self.cfg.puerto_inicio, reuse_address=True).start()
        log.info("Wall-O escuchando en el puerto %d", self.cfg.puerto_inicio)

        parar = asyncio.Event()
        bucle = asyncio.get_running_loop()
        for senal in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError):
                bucle.add_signal_handler(senal, parar.set)

        tareas = [asyncio.create_task(self.escuchar_eventos()), asyncio.create_task(self.revisar_inactividad())]
        await parar.wait()
        for t in tareas:
            t.cancel()
        await self.proxy.cleanup()
        await self.inicio.cleanup()
        await self.registro.cerrar()
        await self.docker.cerrar()


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("WALLO_LOG", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    async def arrancar() -> None:
        # Se construye dentro del bucle: las sesiones HTTP de aiohttp lo necesitan
        await Portal(Config.desde_entorno()).ejecutar()

    asyncio.run(arrancar())


if __name__ == "__main__":
    main()
