# Instalar con Portainer

Wall-O y CompElectrix se instalan como dos **stacks** de Portainer, descargados directamente de GitHub.
Primero Wall-O (crea la red que usan las herramientas) y después CompElectrix.

> Los nombres de los menús son los de Portainer CE 2.x y pueden variar un poco según la versión.

## 0. Si los repositorios son privados: un token de GitHub

Portainer necesita permiso para descargarlos. Si los repositorios son públicos, sáltate este paso.

1. GitHub → tu foto → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
   → **Generate new token**.
2. Nombre: `Portainer`. Caducidad: la que quieras (al caducar habrá que crear otro).
3. **Repository access** → *Only select repositories* → `CompElectrix` y `Wall-O`.
4. **Permissions** → *Repository permissions* → **Contents: Read-only**. Nada más.
5. **Generate token** y guárdalo en 1Password: GitHub no lo vuelve a mostrar.

## 1. Wall-O

Portainer → tu entorno (*local*) → **Stacks** → **Add stack**:

| Campo | Valor |
|---|---|
| Name | `wallo` |
| Build method | **Repository** |
| Repository URL | `https://github.com/iTiton/Wall-O` |
| Repository reference | `refs/heads/main` |
| Compose path | `docker-compose.yml` |
| Authentication | Activado solo si es privado: usuario de GitHub y el token del paso 0 |

**Deploy the stack**. Tarda un par de minutos la primera vez. Después abre `http://IP-DE-LA-RASPBERRY:8100`:
verás el portal vacío.

## 2. CompElectrix

**Stacks** → **Add stack**:

| Campo | Valor |
|---|---|
| Name | `compelectrix` |
| Build method | **Repository** |
| Repository URL | `https://github.com/iTiton/CompElectrix` |
| Repository reference | `refs/heads/main` |
| Compose path | `portainer.yml` |
| Authentication | Igual que en Wall-O |

Opcional, en **Environment variables** → *Add an environment variable*:

- `COMPELECTRIX_DATOS` = ruta completa de una carpeta de la Raspberry (por ejemplo `/home/pi/compelectrix-datos`),
  si quieres los datos en una carpeta fácil de copiar. Si no la pones, se guardan en un volumen de Docker llamado
  `compelectrix-datos`.

**Deploy the stack**. En una Raspberry Pi 4 la primera vez tarda **unos 10 minutos**: compila la interfaz.
Al terminar, CompElectrix aparece en el portal (puerto 8100) y se abre en el **8101**.

## Datos de prueba (opcional)

Para ver la aplicación con datos inventados: Portainer → **Containers** → `compelectrix` → **Console**
→ *User*: `compelectrix`, *Command*: `/bin/sh` → **Connect**, y escribe:

```sh
python -m scripts.demo
```

Solo se cargan si la aplicación está vacía. CompElectrix tiene que estar despierta: ábrela antes desde el portal.

## Actualizar

Portainer → **Stacks** → el stack → **Pull and redeploy** (sección *Git*). Activa la opción de volver a construir la
imagen si aparece. Los datos no se tocan.

## Copia de seguridad

Lo más fácil: en CompElectrix, **Ajustes → Copia de seguridad → Descargar copia**. El navegador descarga un `.zip`
con todos los datos (y tablas para Excel). Para recuperarlos: **Restaurar copia** y elige ese archivo.

Si prefieres copiar los archivos directamente:

- Con la variable `COMPELECTRIX_DATOS`: copia esa carpeta.
- Con el volumen: en la Raspberry, la carpeta `/var/lib/docker/volumes/compelectrix-datos/_data` (hace falta `sudo`).
