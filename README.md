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
- choose `National Gallery London`
- choose `Rijksmuseum`
- choose `Random between museums`
- pause or force an immediate change

Available tray intervals:

- `2` minutes
- `5` minutes
- `15` minutes

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
- Log: `~/.local/share/artwall/artwall.log`

## Notes

- If your main display is not detected correctly, you can test manually with:

```bash
./run.sh once --width 1920 --height 1080
```

- Supported sources:
  - `met`: The Metropolitan Museum of Art
  - `cma`: Cleveland Museum of Art
  - `ngl`: National Gallery London
  - `rijks`: Rijksmuseum
  - `random`: chooses randomly between supported museums
- The default option for a new configuration is `random`.
- This version uses only public-domain artworks with an available image.
- The caption uses font sizes scaled to screen width; the museum line is shown slightly smaller than the artist and date line.
