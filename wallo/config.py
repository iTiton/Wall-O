"""Configuración por variables de entorno (todas opcionales)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _entero(nombre: str, defecto: int) -> int:
    try:
        return int(os.environ.get(nombre, defecto))
    except ValueError:
        return defecto


@dataclass(frozen=True)
class Config:
    puerto_inicio: int = 8100  # página de inicio del portal
    puerto_min: int = 8101  # franja de puertos para las herramientas
    puerto_max: int = 8199
    socket_docker: str = "/var/run/docker.sock"
    dormir_por_defecto: int = 15  # minutos sin uso antes de apagar una herramienta (0 = nunca)
    espera_maxima: int = 90  # segundos esperando a que una herramienta arranque
    intervalo_revision: int = 30  # segundos entre revisiones de inactividad
    red_preferida: str = "wallo"  # red de Docker por la que se llega a las herramientas

    @classmethod
    def desde_entorno(cls) -> Config:
        return cls(
            puerto_inicio=_entero("WALLO_PUERTO", 8100),
            puerto_min=_entero("WALLO_PUERTO_MIN", 8101),
            puerto_max=_entero("WALLO_PUERTO_MAX", 8199),
            socket_docker=os.environ.get("WALLO_DOCKER", "/var/run/docker.sock"),
            dormir_por_defecto=_entero("WALLO_DORMIR_TRAS", 15),
            espera_maxima=_entero("WALLO_ESPERA_MAXIMA", 90),
            intervalo_revision=_entero("WALLO_INTERVALO_REVISION", 30),
            red_preferida=os.environ.get("WALLO_RED", "wallo"),
        )
