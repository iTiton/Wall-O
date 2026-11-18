"""Página de inicio del portal y su pequeña API."""

from __future__ import annotations

import asyncio
import os
from importlib import resources

from aiohttp import web

from . import __version__
from .herramientas import Herramienta, Registro

ESTATICO = resources.files("wallo").joinpath("estatico")


def memoria_propia() -> int | None:
    """Memoria residente del propio portal, en bytes (Linux)."""
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        return None


def a_dict(h: Herramienta, memoria: int | None = None) -> dict:
    return {
        "contenedor": h.contenedor,
        "nombre": h.nombre,
        "descripcion": h.descripcion,
        "icono": h.icono,
        "puerto": h.puerto_publico or h.puerto,
        "estado": h.estado,
        "dormir_tras": h.dormir_tras,
        "minutos_inactiva": round(h.minutos_inactiva(), 1) if h.ejecutando else None,
        "memoria": memoria,
        "error": h.error,
        "version": h.version,
    }


def crear_app_inicio(registro: Registro) -> web.Application:
    app = web.Application()

    async def portada(_req: web.Request) -> web.Response:
        return web.Response(
            text=ESTATICO.joinpath("index.html").read_text(encoding="utf-8"),
            content_type="text/html",
            headers={"Cache-Control": "no-cache"},
        )

    async def listar(_req: web.Request) -> web.Response:
        lista = registro.lista()

        async def mem(h: Herramienta) -> int | None:
            if not h.ejecutando:
                return 0
            try:
                return await asyncio.wait_for(registro.docker.memoria(h.id), 3)
            except asyncio.TimeoutError:
                return None

        memorias = await asyncio.gather(*(mem(h) for h in lista))
        return web.json_response(
            {
                "portal": {"version": __version__, "memoria": memoria_propia()},
                "herramientas": [a_dict(h, m) for h, m in zip(lista, memorias, strict=True)],
            },
            headers={"Cache-Control": "no-store"},
        )

    def _buscar(req: web.Request) -> Herramienta:
        h = registro.por_nombre(req.match_info["contenedor"])
        if h is None:
            raise web.HTTPNotFound(text="Herramienta desconocida")
        return h

    async def despertar(req: web.Request) -> web.Response:
        h = _buscar(req)
        registro.despertar(h)
        return web.json_response(a_dict(h), status=202)

    async def dormir(req: web.Request) -> web.Response:
        h = _buscar(req)
        await registro.dormir(h, "a petición")
        return web.json_response(a_dict(h))

    async def manifiesto(_req: web.Request) -> web.Response:
        return web.json_response(
            {
                "name": "Wall-O",
                "short_name": "Wall-O",
                "start_url": "./",
                "display": "standalone",
                "background_color": "#0b0f14",
                "theme_color": "#0b0f14",
                "icons": [{"src": "estatico/icono.svg", "sizes": "any", "type": "image/svg+xml"}],
            },
            content_type="application/manifest+json",
        )

    app.router.add_get("/", portada)
    app.router.add_get("/api/herramientas", listar)
    app.router.add_post("/api/herramientas/{contenedor}/despertar", despertar)
    app.router.add_post("/api/herramientas/{contenedor}/dormir", dormir)
    app.router.add_get("/manifest.webmanifest", manifiesto)
    app.router.add_static("/estatico/", str(ESTATICO), append_version=False)
    return app
