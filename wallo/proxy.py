"""Proxy inverso: cada puerto de herramienta reenvía a su contenedor, despertándolo si duerme."""

from __future__ import annotations

import asyncio
import logging
from importlib import resources

import aiohttp
from aiohttp import WSMsgType, web

from .herramientas import Herramienta, Registro

log = logging.getLogger("wallo")

SALTO_A_SALTO = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
    "transfer-encoding", "upgrade", "host", "content-length",
}  # fmt: skip
PAGINA_ESPERA = resources.files("wallo").joinpath("estatico/espera.html").read_text(encoding="utf-8")


def es_navegacion(req: web.Request) -> bool:
    """Una página que el navegador abre (no una llamada de la propia aplicación)."""
    if req.method != "GET":
        return False
    destino = req.headers.get("Sec-Fetch-Dest")
    if destino:
        return destino == "document"
    return "text/html" in req.headers.get("Accept", "")


def _cabeceras_salida(req: web.Request) -> dict[str, str]:
    cab = {k: v for k, v in req.headers.items() if k.lower() not in SALTO_A_SALTO}
    ip = req.remote or ""
    previo = req.headers.get("X-Forwarded-For")
    cab["X-Forwarded-For"] = f"{previo}, {ip}" if previo else ip
    cab.setdefault("X-Forwarded-Proto", req.scheme)
    cab["X-Forwarded-Host"] = req.headers.get("X-Forwarded-Host", req.host)
    return cab


def pagina_espera(h: Herramienta) -> web.Response:
    # 200 y no 503: algunos proxies (como el del NAS) sustituyen las páginas de error por las suyas
    return web.Response(
        text=PAGINA_ESPERA.replace("{{nombre}}", _escapar(h.nombre)),
        content_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


def _escapar(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def crear_app_proxy(registro: Registro) -> web.Application:
    cliente = aiohttp.ClientSession(
        auto_decompress=False,  # se reenvía tal cual (gzip incluido)
        timeout=aiohttp.ClientTimeout(total=None, sock_connect=10),
        cookie_jar=aiohttp.DummyCookieJar(),
    )

    async def manejar(req: web.Request) -> web.StreamResponse:
        puerto = req.transport.get_extra_info("sockname")[1] if req.transport else None
        h = registro.por_puerto.get(puerto)
        if h is None:
            raise web.HTTPNotFound(text="No hay ninguna herramienta en este puerto.")

        if req.path == "/__wallo/estado":
            return web.json_response(
                {"nombre": h.nombre, "estado": h.estado, "error": h.error},
                headers={"Cache-Control": "no-store"},
            )

        h.tocar()
        if not h.lista:
            registro.despertar(h)
            if es_navegacion(req):
                return pagina_espera(h)
            if not await registro.esperar_lista(h):
                raise web.HTTPServiceUnavailable(text=f"{h.nombre} no ha arrancado: {h.error or 'sin respuesta'}")

        h.conexiones += 1
        try:
            if req.headers.get("Upgrade", "").lower() == "websocket":
                return await _websocket(req, h, cliente)
            return await _http(req, h, cliente)
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
            # Se apagó o reinició por fuera: se vuelve a comprobar en la siguiente petición
            h.lista = False
            log.info("%s no responde: %s", h.nombre, e)
            if es_navegacion(req):
                registro.despertar(h)
                return pagina_espera(h)
            raise web.HTTPBadGateway(text=f"{h.nombre} no responde.") from e
        finally:
            h.conexiones -= 1
            h.tocar()

    async def cerrar(_app: web.Application) -> None:
        await cliente.close()

    app = web.Application(client_max_size=1024**3)  # subidas grandes (p. ej. facturas en PDF)
    app.router.add_route("*", "/{ruta:.*}", manejar)
    app.on_cleanup.append(cerrar)
    return app


async def _http(req: web.Request, h: Herramienta, cliente: aiohttp.ClientSession) -> web.StreamResponse:
    url = f"http://{h.ip}:{h.puerto_interno}{req.rel_url}"
    cuerpo = req.content if req.can_read_body else None
    async with cliente.request(
        req.method, url, headers=_cabeceras_salida(req), data=cuerpo, allow_redirects=False
    ) as r:
        resp = web.StreamResponse(status=r.status, reason=r.reason)
        for k, v in r.headers.items():
            if k.lower() not in SALTO_A_SALTO:
                resp.headers.add(k, v)
        if r.headers.get("Content-Length"):  # bytes sin descomprimir: la longitud coincide
            resp.content_length = int(r.headers["Content-Length"])
        await resp.prepare(req)
        async for trozo in r.content.iter_chunked(64 * 1024):
            await resp.write(trozo)
            h.tocar()
        await resp.write_eof()
        return resp


async def _websocket(req: web.Request, h: Herramienta, cliente: aiohttp.ClientSession) -> web.WebSocketResponse:
    url = f"ws://{h.ip}:{h.puerto_interno}{req.rel_url}"
    cab = {k: v for k, v in _cabeceras_salida(req).items() if not k.lower().startswith("sec-websocket")}
    protocolos = [p.strip() for p in req.headers.get("Sec-WebSocket-Protocol", "").split(",") if p.strip()]
    async with cliente.ws_connect(url, headers=cab, protocols=protocolos, autoping=False) as destino:
        ws = web.WebSocketResponse(protocols=protocolos, autoping=False)
        await ws.prepare(req)

        async def copiar(origen, hacia) -> None:
            async for m in origen:
                h.tocar()
                if m.type == WSMsgType.TEXT:
                    await hacia.send_str(m.data)
                elif m.type == WSMsgType.BINARY:
                    await hacia.send_bytes(m.data)
                elif m.type == WSMsgType.PING:
                    await hacia.ping(m.data)
                elif m.type == WSMsgType.PONG:
                    await hacia.pong(m.data)
                elif m.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                    break
            await hacia.close()

        await asyncio.gather(copiar(ws, destino), copiar(destino, ws), return_exceptions=True)
        return ws
