# Acceso con HTTPS a través de un NAS Synology

Objetivo: entrar desde el móvil o el portátil, conectado a la VPN del NAS, con direcciones como
`https://tu-nas.synology.me:8100` (portal) y `https://tu-nas.synology.me:8101` (CompElectrix), con candado
y **sin abrir nada a internet**.

```
Móvil ──VPN──► NAS Synology (HTTPS con su certificado) ──http──► Raspberry: Wall-O
                 proxy inverso: una regla por puerto
```

> Los nombres de los menús son los de DSM 7.2 y pueden variar un poco según la versión.
> Donde pone `tu-nas.synology.me`, usa tu dirección de Synology. Donde pone `192.168.1.50`, usa la IP de tu Raspberry.

## 0. Antes de empezar

- La Raspberry debe tener **siempre la misma IP**. En el router, reserva su IP (suele llamarse "DHCP estática"
  o "reserva de IP"), o pregúntame y lo vemos.
- Usa la franja **8100-8199**. Comprueba al final (paso 5) que el router **no** la redirige al NAS.

## 1. Certificado

Panel de control → Seguridad → **Certificado**. Debe aparecer el de `tu-nas.synology.me` (Let's Encrypt).
Si está, no hay que hacer nada más aquí; lo asignaremos en el paso 3.

## 2. Proxy inverso: una regla por puerto

Panel de control → Portal de inicio de sesión → Avanzado → **Proxy inverso** → Crear.

Regla para la página de inicio:

| Campo | Valor |
|---|---|
| Nombre | `Wall-O` |
| Origen · Protocolo | HTTPS |
| Origen · Nombre de host | `tu-nas.synology.me` |
| Origen · Puerto | `8100` |
| Destino · Protocolo | HTTP |
| Destino · Nombre de host | `192.168.1.50` |
| Destino · Puerto | `8100` |

En la pestaña **Encabezado personalizado** → Crear → **WebSocket** (añade dos líneas solas) → Guardar.

Repite con el **mismo número** de puerto de origen y destino para cada herramienta:
`8101` → CompElectrix, `8102` → la siguiente…

## 3. Asignar el certificado

Panel de control → Seguridad → Certificado → **Configuración**. En cada regla nueva del proxy inverso
(`tu-nas.synology.me:8100`, `:8101`…), elige el certificado de `tu-nas.synology.me` → Aceptar.

## 4. Que el nombre apunte al NAS dentro de la VPN

`tu-nas.synology.me` apunta a la IP pública de tu casa. Dentro de la VPN tiene que apuntar al NAS, para que
el tráfico no salga a internet y vuelva. Para eso:

1. Centro de paquetes → instala **DNS Server**.
2. DNS Server → Zonas → Crear → **Zona maestra**:
   - Dominio: `tu-nas.synology.me`
   - IP del servidor DNS maestro: la IP del NAS en casa
3. Entra en la zona → Crear → **Registro A**: nombre vacío (la propia zona) → IP del NAS en casa.
4. DNS Server → Resolución → activa **Habilitar reenviadores** (por ejemplo `1.1.1.1` y `9.9.9.9`),
   para que el resto de direcciones sigan funcionando.
5. Haz que los dispositivos de la VPN usen el NAS como DNS. **Este paso depende del tipo de VPN**
   (OpenVPN o L2TP/IPSec): dime cuál usas y lo completamos.

## 5. Comprobación de seguridad (importante)

1. En el móvil, **desconecta la wifi y la VPN** (solo datos móviles).
2. Abre `https://tu-nas.synology.me:8100`.
3. **No debe cargar.** Si carga, el router está redirigiendo ese puerto: avísame antes de seguir.
4. Conecta la VPN y vuelve a abrirlo: ahora **sí** debe cargar, con candado.

## 6. Como una app en el móvil

En el iPhone, abre `https://tu-nas.synology.me:8100` en Safari → Compartir → **Añadir a pantalla de inicio**.
