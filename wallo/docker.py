"""Cliente mínimo de la API de Docker por su socket Unix (sin dependencias extra).

Seguridad: el acceso al socket de Docker equivale a ser administrador de la
máquina. Por eso este cliente SOLO lista, arranca, para o consulta contenedores
que tengan la etiqueta `wallo.activar=true`, y lo vuelve a comprobar antes de
cada acción.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import aiohttp

API = "http://docker/v1.41"
ETIQUETA = "wallo.activar"
FILTRO = json.dumps({"label": [f"{ETIQUETA}=true"]})


class ErrorDocker(Exception):
    pass


class Docker:
    def __init__(self, socket: str):
        self.socket = socket
        self._sesion: aiohttp.ClientSession | None = None

    @property
    def sesion(self) -> aiohttp.ClientSession:
        if self._sesion is None or self._sesion.closed:
            self._sesion = aiohttp.ClientSession(
                connector=aiohttp.UnixConnector(path=self.socket),
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=5),
            )
        return self._sesion

    async def cerrar(self) -> None:
        if self._sesion:
            await self._sesion.close()

    async def _json(self, metodo: str, ruta: str, **kw):
        try:
            async with self.sesion.request(metodo, f"{API}{ruta}", **kw) as r:
                if r.status >= 400:
                    raise ErrorDocker(f"Docker {r.status}: {(await r.text())[:200]}")
                if r.status in (204, 304):
                    return None
                return await r.json()
        except aiohttp.ClientError as e:
            raise ErrorDocker(f"No se puede hablar con Docker ({self.socket}): {e}") from e

    async def listar(self) -> list[dict]:
        """Contenedores marcados para el portal, encendidos o apagados."""
        return await self._json("GET", "/containers/json", params={"all": "1", "filters": FILTRO})

    async def inspeccionar(self, id_: str) -> dict:
        info = await self._json("GET", f"/containers/{id_}/json")
        if (info.get("Config", {}).get("Labels") or {}).get(ETIQUETA) != "true":
            raise ErrorDocker(f"El contenedor {id_} no está marcado con {ETIQUETA}=true")
        return info

    async def arrancar(self, id_: str) -> None:
        await self.inspeccionar(id_)
        await self._json("POST", f"/containers/{id_}/start")

    async def parar(self, id_: str, segundos: int = 10) -> None:
        await self.inspeccionar(id_)
        await self._json("POST", f"/containers/{id_}/stop", params={"t": str(segundos)})

    async def memoria(self, id_: str) -> int | None:
        """Memoria en uso (bytes), descontando la caché de disco como hace `docker stats`."""
        try:
            s = await self._json("GET", f"/containers/{id_}/stats", params={"stream": "false", "one-shot": "true"})
        except ErrorDocker:
            return None
        m = (s or {}).get("memory_stats") or {}
        uso = m.get("usage")
        if uso is None:
            return None
        st = m.get("stats") or {}
        return uso - st.get("inactive_file", st.get("total_inactive_file", 0))

    async def asegurar_red(self, nombre: str) -> bool:
        """Crea la red de las herramientas si no existe. Devuelve True si la ha creado."""
        try:
            await self._json("GET", f"/networks/{nombre}")
            return False
        except ErrorDocker:
            await self._json(
                "POST", "/networks/create",
                json={"Name": nombre, "Driver": "bridge", "Labels": {"wallo.red": "true"}},
            )  # fmt: skip
            return True

    async def eventos(self) -> AsyncIterator[dict]:
        """Eventos de los contenedores marcados (arranque, parada, creación, borrado…)."""
        filtros = json.dumps({"type": ["container"], "label": [f"{ETIQUETA}=true"]})
        try:
            async with self.sesion.get(f"{API}/events", params={"filters": filtros}) as r:
                async for linea in r.content:
                    if linea.strip():
                        yield json.loads(linea)
        except aiohttp.ClientError as e:
            raise ErrorDocker(f"Se perdió la conexión con Docker: {e}") from e
