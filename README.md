# artwall

`artwall` rotates the KDE wallpaper using museum artworks and overlays a discreet caption in the lower-left corner with title, artist, date, and museum.

## Current Status

- Target environment: KDE Plasma on Linux
- Wallpaper change command: `plasma-apply-wallpaperimage`
- Scheduling: `systemd --user`

The project structure is ready to support additional sources. The original Museo del Prado idea is feasible, but its website is protected by Cloudflare and is not a good base for a first robust automation.

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

If you run `./run.sh` without arguments, it also starts in tray mode.

From the tray icon you can:

- change the rotation interval
- choose `The Met`
- choose `Cleveland Museum of Art`
- choose `Art Institute of Chicago`
- choose `Harvard Art Museums`
- choose `National Gallery London`
- choose `Rijksmuseum`
- choose `Random between museums`
- pause or force an immediate change

Available tray intervals:

- `2` minutes
- `5` minutes
- `10` minutes

## Manual Command-Line Usage

```bash
./run.sh init --minutes 2 --source random
./run.sh once
```

## Install the Timer

```bash
./install_systemd.sh 2
```

This creates and enables:

- `~/.config/systemd/user/artwall.service`
- `~/.config/systemd/user/artwall.timer`

## Autostart with Tray

```bash
./install_autostart.sh
```

This creates:

- `~/.config/autostart/artwall.desktop`

## Paths

- Configuration: `~/.config/artwall/config.json`
- Image cache: `~/.local/share/artwall/cache`
- Rendered wallpapers: `~/.local/share/artwall/rendered`
- Maximum rendered wallpapers kept: `10`
- Current state: `~/.local/share/artwall/current.json`
- Recent artwork history: `~/.local/share/artwall/recent-artworks.json`
- Log: `~/.local/share/artwall/artwall.log`

## Configuration

The configuration file is stored at `~/.config/artwall/config.json`.

Current supported keys:

- `interval_minutes`
- `source`
- `keep_rendered`
- `paused`
- `avoid_repeat_days`
- `history_retention_days`
- `cache_max_mb`
- `harvard_api_key`

Default values for a new configuration:

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

`avoid_repeat_days` defines how long artwall tries not to repeat the same artwork from the same museum.

`history_retention_days` defines how long seen-artwork entries are kept before they are purged automatically.

`cache_max_mb` defines the maximum image cache size. If the image cache exceeds this limit, artwall deletes the oldest cached images until it is under the limit.

`harvard_api_key` enables the optional Harvard Art Museums source. You can also set `ARTWALL_HARVARD_API_KEY` in the environment instead of storing the key in the config file.
Harvard candidates are checked for image downloadability before they are accepted, so network-specific `403` responses are skipped instead of being returned as usable artworks.

`recent-artworks.json` stores the seen-artwork history by museum using the format `object_id -> ISO 8601 UTC timestamp`.

## Notes

- If your main display is not detected correctly, you can test manually with:

```bash
./run.sh once --width 1920 --height 1080
```

- Supported sources:
  - `met`: The Metropolitan Museum of Art
  - `cma`: Cleveland Museum of Art
  - `aic`: Art Institute of Chicago
  - `harvard`: Harvard Art Museums
  - `ngl`: National Gallery London
  - `rijks`: Rijksmuseum
  - `random`: chooses randomly between supported museums
- The default option for a new configuration is `random`.
- Existing configurations are migrated automatically when new config keys are introduced.
- On this machine, `avoid_repeat_days` is currently set to `30`.
- On this machine, `cache_max_mb` is currently set to `500`.
- This version uses only public-domain artworks with an available image.
- The caption uses font sizes scaled to screen width; the museum line is shown slightly smaller than the artist and date line.
