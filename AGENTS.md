# Artwall: notas para agentes

## Fondo y pantallas

Artwall genera un único fondo y KDE lo aplica a todas las pantallas. Para evitar
que una imagen 16:10 recorte la leyenda inferior al mostrarse en monitores 16:9,
la detección de resolución prioriza el monitor externo habilitado con mayor número
de píxeles. Si no hay externos, usa la pantalla habilitada de mayor resolución.

- `detect_screen_size()` consulta primero `kscreen-doctor -o` y después
  `xrandr --current`.
- `parse_kscreen_screen_size()` y `parse_xrandr_screen_size()` extraen las
  resoluciones activas.
- `preferred_screen_size()` identifica paneles internos por conectores `eDP`,
  `LVDS` o `DSI` y prefiere los demás.
- Mantener la leyenda en la zona inferior: al usar un fondo 16:9 también en un
  panel 16:10, KDE puede recortar laterales, pero no la parte inferior.

## Verificación

Tras modificar esta lógica, comprobar al menos:

```bash
python3 -m py_compile artwall.py
```

Y validar con salidas simuladas de KScreen y xrandr que una pantalla externa
1920x1080 se elige frente a un panel interno 1536x960. Para aplicar un fondo
inmediatamente, ejecutar `./run.sh once`; necesita acceso a la sesión de KDE y
red para descargar una obra si no está disponible en caché.
