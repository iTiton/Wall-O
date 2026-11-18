"""Pruebas del portal con un Docker simulado y una herramienta real (servidor aiohttp local)."""

import asyncio
import time

import aiohttp
import pytest
from aiohttp import web

from wallo.config import Config
from wallo.docker import ErrorDocker
from wallo.herramientas import Registro, desde_etiquetas
from wallo.inicio import crear_app_inicio
from wallo.proxy import crear_app_proxy, es_navegacion

CFG = Config(espera_maxima=5, puerto_min=8101, puerto_max=8199)


def contenedor(id_="c1", puerto="8101", estado="exited", **extra):
    extra = {(k if k.startswith("wallo.") else f"wallo.{k}"): v for k, v in extra.items()}
    etiquetas = {"wallo.activar": "true", "wallo.puerto": puerto, "wallo.nombre": "Prueba", **extra}
    return {"Id": id_, "Names": [f"/{id_}"], "Labels": etiquetas, "State": estado}


class DockerFalso:
    """Imita la API de Docker: arrancar enciende la herramienta de prueba."""

    def __init__(self, contenedores, puerto_herramienta):
        self.contenedores = contenedores
        self.puerto = puerto_herramienta
        self.acciones = []

    async def listar(self):
        return self.contenedores

    async def inspeccionar(self, id_):
        c = next((c for c in self.contenedores if c["Id"] == id_), None)
        if c is None or c["Labels"].get("wallo.activar") != "true":
            raise ErrorDocker("no marcado")
        ip = "127.0.0.1" if c["State"] == "running" else ""
        return {"NetworkSettings": {"Networks": {"wallo": {"IPAddress": ip}}}}

    async def arrancar(self, id_):
        await self.inspeccionar(id_)
        self.acciones.append(("arrancar", id_))
        next(c for c in self.contenedores if c["Id"] == id_)["State"] = "running"

    async def parar(self, id_):
        await self.inspeccionar(id_)
        self.acciones.append(("parar", id_))
        next(c for c in self.contenedores if c["Id"] == id_)["State"] = "exited"

    async def memoria(self, id_):
        return 50 * 1024 * 1024


async def app_herramienta():
    """Herramienta de prueba: responde texto, hace eco de cabeceras, comprime y tiene websocket."""

    async def raiz(req):
        return web.Response(
            text=f"hola {req.path_qs} {req.headers.get('X-Forwarded-For', '')} portal={req.headers.get('X-Wallo-Portal')}"
        )

    async def subir(req):
        return web.Response(text=str(len(await req.read())))

    async def ws(req):
        s = web.WebSocketResponse()
        await s.prepare(req)
        async for m in s:
            await s.send_str("eco:" + m.data)
        return s

    async def comprimido(req):
        r = web.Response(text="x" * 5000)
        r.enable_compression()
        return r

    async def salud(_req):
        return web.json_response({"estado": "ok", "version": "9.99"})

    app = web.Application()
    app.router.add_get("/salud", salud)
    app.router.add_get("/ws", ws)
    app.router.add_get("/comprimido", comprimido)
    app.router.add_post("/subir", subir)
    app.router.add_route("*", "/{r:.*}", raiz)
    return app


@pytest.fixture
async def entorno(aiohttp_server):
    herramienta = await aiohttp_server(await app_herramienta())
    docker = DockerFalso(
        [contenedor(puerto_interno=str(herramienta.port), dormir_tras="1", salud="/salud")], herramienta.port
    )
    registro = Registro(CFG, docker)
    await registro.sincronizar()
    # El proxy distingue la herramienta por el puerto local; en las pruebas lo forzamos
    servidor = await aiohttp_server(crear_app_proxy(registro))
    registro.por_puerto = {servidor.port: registro.por_puerto[8101]}
    registro.por_puerto[servidor.port].puerto = servidor.port
    yield registro, docker, servidor
    await registro.cerrar()


def test_etiquetas():
    h = desde_etiquetas(contenedor(puerto="8105", **{"wallo.dormir_tras": "0", "wallo.salud": "api/salud"}), CFG)
    assert h.puerto == 8105 and h.dormir_tras == 0 and h.salud == "/api/salud" and h.puerto_interno == 80
    assert desde_etiquetas(contenedor(puerto="8100"), CFG) is None  # el de la portada no se puede usar
    assert desde_etiquetas(contenedor(puerto="22"), CFG) is None
    assert desde_etiquetas(contenedor(puerto="abc"), CFG) is None


def test_navegacion():
    from aiohttp.test_utils import make_mocked_request

    assert es_navegacion(make_mocked_request("GET", "/", headers={"Sec-Fetch-Dest": "document"}))
    assert not es_navegacion(make_mocked_request("GET", "/api", headers={"Sec-Fetch-Dest": "empty"}))
    assert es_navegacion(make_mocked_request("GET", "/", headers={"Accept": "text/html,*/*"}))
    assert not es_navegacion(make_mocked_request("POST", "/", headers={"Accept": "text/html"}))


async def test_despierta_al_navegar_y_reenvia(entorno):
    registro, docker, servidor = entorno
    async with aiohttp.ClientSession() as c:
        url = f"http://127.0.0.1:{servidor.port}"
        # Navegador: página de espera inmediata y arranque en segundo plano
        r = await c.get(f"{url}/pagina?x=1", headers={"Sec-Fetch-Dest": "document"})
        assert r.status == 200 and "Despertando Prueba" in await r.text()
        assert ("arrancar", "c1") in docker.acciones
        for _ in range(50):
            e = await (await c.get(f"{url}/__wallo/estado")).json()
            if e["estado"] == "activa":
                break
            await asyncio.sleep(0.1)
        assert e["estado"] == "activa"
        assert next(iter(registro.por_puerto.values())).version == "9.99"
        # Ya despierta: reenvía con la ruta, la consulta y X-Forwarded-For
        r = await c.get(f"{url}/pagina?x=1", headers={"Sec-Fetch-Dest": "document"})
        texto = await r.text()
        assert texto.startswith("hola /pagina?x=1 127.0.0.1") and texto.endswith("portal=8100")
        # Cuerpo de subida y respuesta comprimida sin tocar
        r = await c.post(f"{url}/subir", data=b"a" * 200_000)
        assert await r.text() == "200000"
        r = await c.get(f"{url}/comprimido", headers={"Accept-Encoding": "gzip"}, auto_decompress=False)
        assert r.headers["Content-Encoding"] == "gzip" and len(await r.read()) < 5000


async def test_llamada_de_api_espera_a_que_despierte(entorno):
    registro, docker, servidor = entorno
    async with aiohttp.ClientSession() as c:
        r = await c.get(f"http://127.0.0.1:{servidor.port}/api/datos", headers={"Sec-Fetch-Dest": "empty"})
        assert r.status == 200 and (await r.text()).startswith("hola /api/datos")


async def test_websocket(entorno):
    registro, docker, servidor = entorno
    await registro.esperar_lista(next(iter(registro.por_puerto.values())))
    async with aiohttp.ClientSession() as c, c.ws_connect(f"http://127.0.0.1:{servidor.port}/ws") as ws:
        await ws.send_str("hola")
        assert (await ws.receive_str()) == "eco:hola"


async def test_duerme_por_inactividad_pero_no_con_conexiones(entorno):
    registro, docker, _ = entorno
    h = next(iter(registro.por_puerto.values()))
    await registro.esperar_lista(h)
    h.ultima_actividad = time.monotonic() - 120  # 2 min sin uso; dormir_tras=1
    h.conexiones = 1
    await registro.revisar_inactivas()
    assert ("parar", "c1") not in docker.acciones
    h.conexiones = 0
    await registro.revisar_inactivas()
    assert ("parar", "c1") in docker.acciones and h.estado == "dormida"


async def test_no_toca_contenedores_sin_etiqueta(entorno):
    registro, docker, _ = entorno
    docker.contenedores.append({"Id": "ajeno", "Names": ["/ajeno"], "Labels": {}, "State": "running"})
    with pytest.raises(ErrorDocker):
        await docker.parar("ajeno")


async def test_eventos():
    docker = DockerFalso([contenedor(estado="running")], 1)
    registro = Registro(CFG, docker)
    registro.por_puerto = {8101: desde_etiquetas(contenedor(estado="running"), CFG)}
    h = registro.por_puerto[8101]
    h.lista = True
    assert registro.aplicar_evento({"Action": "die", "id": "c1"}) is False
    assert not h.ejecutando and not h.lista
    assert registro.aplicar_evento({"Action": "create", "id": "otro"}) is True
    await registro.cerrar()


async def test_portada(aiohttp_client):
    docker = DockerFalso([contenedor(estado="running", **{"wallo.descripcion": "Algo", "wallo.icono": "rayo"})], 1)
    registro = Registro(CFG, docker)
    await registro.sincronizar()
    c = await aiohttp_client(crear_app_inicio(registro))
    assert "Wall-O" in await (await c.get("/")).text()
    d = await (await c.get("/api/herramientas")).json()
    assert d["herramientas"][0]["nombre"] == "Prueba" and d["herramientas"][0]["memoria"] == 50 * 1024 * 1024
    r = await c.post("/api/herramientas/c1/dormir")
    assert r.status == 200 and ("parar", "c1") in docker.acciones
    assert (await c.post("/api/herramientas/nada/dormir")).status == 404
    assert (await c.get("/estatico/app.js")).status == 200
    await registro.cerrar()
