# artwall

[English](README.md) · [Español](README.es.md)

`artwall` cambia el fondo de KDE usando obras de museos y muestra una leyenda discreta en la esquina inferior izquierda con el título, el artista, la fecha y el museo.

## Current Status

- Entorno objetivo: KDE Plasma en Linux
- Comando para cambiar el fondo: `plasma-apply-wallpaperimage`
- Programación: `systemd --user`

La estructura del proyecto permite añadir más fuentes. La idea original de usar el Museo del Prado es viable, pero su web está protegida por Cloudflare y no es una buena base para una primera automatización robusta.

## Dependencies

```bash
sudo apt install -y \
  python3 python3-requests python3-pil plasma-workspace \
  python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1
```

## Tray Mode

```bash
./run.sh tray
```

Si ejecutas `./run.sh` sin argumentos, también se inicia el modo bandeja.

Desde el icono de la bandeja puedes:

- cambiar el intervalo de rotación
- elegir `The Met`
- elegir `Cleveland Museum of Art`
- elegir `Art Institute of Chicago`
- elegir `Harvard Art Museums`
- elegir `National Gallery London`
- elegir `Rijksmuseum`
- elegir `Random between museums`
- pausar o forzar un cambio inmediato

Available tray intervals:

- `2` minutos
- `5` minutos
- `10` minutos

## Manual Command-Line Usage

```bash
./run.sh init --minutes 2 --source random
./run.sh once
```

## Install the Timer

```bash
./install_systemd.sh 2
```

Esto crea y activa:

- `~/.config/systemd/user/artwall.service`
- `~/.config/systemd/user/artwall.timer`

## Autostart with Tray

```bash
./install_autostart.sh
```

Esto crea:

- `~/.config/autostart/artwall.desktop`
- `~/.local/share/applications/artwall.desktop`

La primera entrada inicia artwall en modo bandeja al comenzar la sesión de KDE; la
segunda lo hace disponible en el menú de aplicaciones de KDE.

## Troubleshooting autostart

La entrada de bandeja es iniciada por KDE desde `~/.config/autostart/artwall.desktop`.
Si se cierra durante el arranque, consulta la unidad generada de la sesión y el
registro de la aplicación:

```bash
systemctl --user status app-artwall@autostart.service --no-pager
tail -80 ~/.local/share/artwall/artwall.log
```

En Debian o Ubuntu, el inicio de la bandeja requiere el paquete del sistema
`gir1.2-ayatanaappindicator3-0.1` además de las dependencias de Python.

## Paths

- Configuración: `~/.config/artwall/config.json`
- Caché de imágenes: `~/.local/share/artwall/cache`
- Fondos renderizados: `~/.local/share/artwall/rendered`
- Máximo de fondos renderizados conservados: `10`
- Estado actual: `~/.local/share/artwall/current.json`
- Historial reciente de obras: `~/.local/share/artwall/recent-artworks.json`
- Registro: `~/.local/share/artwall/artwall.log`

## Configuration

El archivo de configuración se guarda en `~/.config/artwall/config.json`.

Claves disponibles:

- `interval_minutes`
- `source`
- `keep_rendered`
- `paused`
- `avoid_repeat_days`
- `history_retention_days`
- `cache_max_mb`
- `harvard_api_key`

Valores predeterminados para una configuración nueva:

```json
{
  "interval_minutes": 2,
  "source": "random",
  "keep_rendered": 10,
  "paused": false,
  "avoid_repeat_days": 7,
  "history_retention_days": 60,
  "cache_max_mb": 500,
  "harvard_api_key": ""
}
```

`avoid_repeat_days` define durante cuánto tiempo artwall intenta no repetir la misma obra del mismo museo.

`history_retention_days` define cuánto tiempo se conservan las obras vistas antes de eliminarlas automáticamente.

`cache_max_mb` define el tamaño máximo de la caché de imágenes. Si se supera este límite, artwall elimina las imágenes más antiguas hasta quedar por debajo.

`harvard_api_key` activa opcionalmente la fuente Harvard Art Museums. También puedes establecer `ARTWALL_HARVARD_API_KEY` en el entorno en lugar de guardar la clave en el archivo de configuración.
Las obras de Harvard se comprueban antes de aceptarlas para verificar que sus imágenes se pueden descargar; las respuestas `403` se descartan.

`recent-artworks.json` guarda el historial de obras vistas por museo con el formato `object_id -> ISO 8601 UTC timestamp`.

## Notes

- Si no se detecta correctamente la pantalla principal, puedes probar manualmente con:

```bash
./run.sh once --width 1920 --height 1080
```

- Fuentes compatibles:
  - `met`: The Metropolitan Museum of Art
  - `cma`: Cleveland Museum of Art
  - `aic`: Art Institute of Chicago
  - `harvard`: Harvard Art Museums
  - `ngl`: National Gallery London
  - `rijks`: Rijksmuseum
  - `random`: elige aleatoriamente entre los museos compatibles
- La opción predeterminada para una configuración nueva es `random`.
- Las configuraciones existentes se migran automáticamente al introducir nuevas claves.
- En este equipo, `avoid_repeat_days` está establecido actualmente en `30`.
- En este equipo, `cache_max_mb` está establecido actualmente en `500`.
- Esta versión solo usa obras de dominio público con una imagen disponible.
- La leyenda usa tamaños de fuente escalados según el ancho de la pantalla; la línea del museo se muestra algo más pequeña que la del artista y la fecha.

## Idioma

artwall admite español e inglés. El menú de la bandeja incluye **Idioma → Español / English**; el idioma elegido se guarda en `~/.config/artwall/config.json` y se reutiliza en los siguientes arranques. En el primer arranque, si no existe configuración, artwall sigue `LC_MESSAGES`, `LC_ALL` o `LANG` cuando empiezan por `en`; en caso contrario usa español.
