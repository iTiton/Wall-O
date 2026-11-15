# Cómo preparar una herramienta para Wall-O

Cualquier aplicación web en Docker sirve. Para que funcione bien detrás del portal:

1. **Escucha en un puerto dentro del contenedor** (`wallo.puerto_interno`) y **no publiques puertos**:
   se entra solo por el portal.
2. **Ten una ruta de salud** (`wallo.salud`, por ejemplo `/api/salud`) que responda en cuanto la aplicación
   pueda atender peticiones. Wall-O espera a que responda antes de mostrarla.
3. **Arranca rápido**: es lo que tarda en despertar. En una Raspberry Pi, apunta a menos de 5 segundos.
4. **No dependas de estar siempre encendida**. Si necesitas datos actualizados (precios, copias…),
   complétalos **al abrirla**, como hace CompElectrix con el PVPC, en lugar de con tareas periódicas.
5. **Guarda los datos en un volumen** (`./data:/data`): el contenedor se apaga y se enciende a menudo.
6. **Termina limpio con SIGTERM** (Docker lo envía al dormirla) y escribe en disco de forma segura.
7. **Usa las cabeceras estándar del proxy** si necesitas la dirección original: `X-Forwarded-For`,
   `X-Forwarded-Proto` y `X-Forwarded-Host`.
8. **WebSockets**: funcionan sin hacer nada; una conexión abierta mantiene despierta la herramienta.

## Mantenerlo limpio

- **Un puerto por herramienta**, apuntado en esta tabla, para no repetirlos:

  | Puerto | Herramienta |
  |---|---|
  | 8100 | Wall-O (página de inicio) |
  | 8101 | CompElectrix |
  | 8102 | (libre) |

- Nombres de contenedor cortos y en minúsculas (`container_name: compelectrix`).
- `restart: unless-stopped`: si Wall-O la duerme, sigue dormida tras reiniciar la Raspberry.
- Logs pequeños: `logging: { driver: json-file, options: { max-size: "1m", max-file: "2" } }`.
