#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import re
import subprocess
import sys
import textwrap
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

AppIndicator = None
GLib = None
Gtk = None
HAS_TRAY_SUPPORT = False

APP_ID = "artwall"
APP_NAME = "artwall"
USER_AGENT = "artwall/0.2 (+personal KDE wallpaper rotator)"

CONFIG_DIR = Path.home() / ".config" / APP_ID
DATA_DIR = Path.home() / ".local" / "share" / APP_ID
CACHE_DIR = DATA_DIR / "cache"
RENDER_DIR = DATA_DIR / "rendered"
STATE_PATH = DATA_DIR / "current.json"
HISTORY_PATH = DATA_DIR / "recent-artworks.json"
LOG_PATH = DATA_DIR / "artwall.log"
CONFIG_PATH = CONFIG_DIR / "config.json"
ICON_NAME = "artwall-tray"
ICON_PATH = Path(__file__).resolve().with_name(f"{ICON_NAME}.svg")
MET_OBJECTS_CACHE = CACHE_DIR / "met-object-ids.json"
NGL_URLS_CACHE = CACHE_DIR / "ngl-artwork-urls.json"
RIJKS_PAGES_CACHE = CACHE_DIR / "rijks-page-urls.json"
FONT_PATHS = [
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
]

REQUEST_TIMEOUT = 30
MET_SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"
CMA_ARTWORKS_URL = "https://openaccess-api.clevelandart.org/api/artworks"
RIJKS_SEARCH_URL = "https://data.rijksmuseum.nl/search/collection?type=painting&imageAvailable=true"
RESAMPLE_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")

MUSEUM_LABELS = {
    "met": "The Met",
    "cma": "Cleveland Museum of Art",
    "ngl": "National Gallery London",
    "rijks": "Rijksmuseum",
    "random": "Aleatorio entre museos",
}
SUPPORTED_MUSEUMS = ("met", "cma", "ngl", "rijks")
TRAY_INTERVAL_OPTIONS = (2, 5, 15)
KDE_APPLY_RETRIES = 2
KDE_APPLY_RETRY_DELAY_SECONDS = 3
TRAY_STARTUP_DELAY_SECONDS = 15
RECENT_HISTORY_SIZE = 30
RECENT_SELECTION_ATTEMPTS = 12
LOG_MAX_BYTES = 1_048_576
LOG_BACKUP_COUNT = 4


@dataclass
class Settings:
    interval_minutes: int = 2
    source: str = "random"
    screen_width: int = 0
    screen_height: int = 0
    keep_rendered: int = 10
    paused: bool = False


@dataclass
class Artwork:
    source: str
    object_id: int
    title: str
    author: str
    year: str
    image_url: str
    page_url: str


class ArtwallError(RuntimeError):
    pass


def load_tray_modules() -> None:
    global AppIndicator, GLib, Gtk, HAS_TRAY_SUPPORT
    if HAS_TRAY_SUPPORT:
        return

    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as AppIndicatorModule
        from gi.repository import GLib as GLibModule
        from gi.repository import Gtk as GtkModule
    except (ImportError, ValueError) as exc:
        raise ArtwallError(
            "Modo bandeja no disponible. Instala python3-gi, gir1.2-gtk-3.0 y "
            "gir1.2-ayatanaappindicator3-0.1."
        ) from exc

    AppIndicator = AppIndicatorModule
    GLib = GLibModule
    Gtk = GtkModule
    HAS_TRAY_SUPPORT = True


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    RENDER_DIR.mkdir(parents=True, exist_ok=True)


def rotate_log_if_needed() -> None:
    try:
        if not LOG_PATH.exists() or LOG_PATH.stat().st_size < LOG_MAX_BYTES:
            return
    except OSError:
        return

    oldest_backup = LOG_PATH.with_name(f"{LOG_PATH.name}.{LOG_BACKUP_COUNT}")
    oldest_backup.unlink(missing_ok=True)

    for index in range(LOG_BACKUP_COUNT - 1, 0, -1):
        source = LOG_PATH.with_name(f"{LOG_PATH.name}.{index}")
        target = LOG_PATH.with_name(f"{LOG_PATH.name}.{index + 1}")
        if source.exists():
            source.replace(target)

    try:
        LOG_PATH.replace(LOG_PATH.with_name(f"{LOG_PATH.name}.1"))
    except OSError:
        pass


def log_message(message: str) -> None:
    ensure_dirs()
    rotate_log_if_needed()
    timestamp = datetime.now().isoformat(timespec="seconds")
    try:
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {message}\n")
    except OSError:
        pass


def log_selection_metrics(source: str, **metrics: Any) -> None:
    parts = [f"source={source}"]
    parts.extend(f"{key}={value}" for key, value in metrics.items())
    log_message("[artwall] selection " + " ".join(parts))


def normalize_source(source: str) -> str:
    source = str(source or "random").strip().lower()
    if source == "aic":
        return "cma"
    if source in MUSEUM_LABELS:
        return source
        return "random"


def load_settings() -> Settings:
    if not CONFIG_PATH.exists():
        settings = Settings()
        save_settings(settings)
        return settings

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtwallError(f"No se pudo leer la configuracion: {exc}") from exc

    return Settings(
        interval_minutes=max(1, int(data.get("interval_minutes", 2))),
        source=normalize_source(data.get("source", "random")),
        screen_width=max(0, int(data.get("screen_width", 0))),
        screen_height=max(0, int(data.get("screen_height", 0))),
        keep_rendered=max(3, int(data.get("keep_rendered", 10))),
        paused=bool(data.get("paused", False)),
    )


def save_settings(settings: Settings) -> None:
    CONFIG_PATH.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=APP_NAME, description="Wallpaper rotator de arte para KDE.")
    subparsers = parser.add_subparsers(dest="command", required=False)

    once_parser = subparsers.add_parser("once", help="Descarga una obra, la compone y la aplica.")
    once_parser.add_argument("--width", type=int, default=0, help="Ancho objetivo opcional.")
    once_parser.add_argument("--height", type=int, default=0, help="Alto objetivo opcional.")

    init_parser = subparsers.add_parser("init", help="Crea la configuracion inicial.")
    init_parser.add_argument("--minutes", type=int, default=2, help="Intervalo por defecto.")
    init_parser.add_argument(
        "--source",
        choices=tuple(MUSEUM_LABELS.keys()),
        default="random",
        help="Fuente inicial de imagenes.",
    )

    install_parser = subparsers.add_parser("install-systemd", help="Instala servicio y timer de usuario.")
    install_parser.add_argument("--minutes", type=int, default=2, help="Minutos entre cambios.")

    subparsers.add_parser("status", help="Muestra la obra actual y rutas principales.")
    subparsers.add_parser("tray", help="Inicia la aplicacion residente en la bandeja del sistema.")

    args = parser.parse_args()
    if args.command is None:
        args.command = "tray"
    return args


def request_json(url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return response.json()


def load_cached_met_ids() -> list[int] | None:
    if not MET_OBJECTS_CACHE.exists():
        return None

    try:
        payload = json.loads(MET_OBJECTS_CACHE.read_text(encoding="utf-8"))
        cached_at = datetime.fromisoformat(payload["cached_at"])
        if datetime.now(timezone.utc) - cached_at > timedelta(days=7):
            return None
        ids = payload.get("object_ids", [])
        return [int(object_id) for object_id in ids if isinstance(object_id, int)]
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def save_cached_met_ids(object_ids: list[int]) -> None:
    payload = {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "object_ids": object_ids,
    }
    MET_OBJECTS_CACHE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_cached_urls(cache_path: Path, *, max_age_days: int = 7) -> list[str] | None:
    if not cache_path.exists():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        cached_at = datetime.fromisoformat(payload["cached_at"])
        if datetime.now(timezone.utc) - cached_at > timedelta(days=max_age_days):
            return None
        urls = payload.get("urls", [])
        return [str(url) for url in urls if str(url).startswith("https://")]
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def save_cached_urls(cache_path: Path, urls: list[str]) -> None:
    payload = {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "urls": urls,
    }
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def fetch_rijks_page_urls() -> list[str]:
    cached = load_cached_urls(RIJKS_PAGES_CACHE, max_age_days=14)
    if cached:
        return cached

    payload = request_json(RIJKS_SEARCH_URL)
    page_urls: list[str] = []
    seen_urls: set[str] = set()

    while True:
        page_id = clean_text(payload.get("id"))
        if page_id and page_id not in seen_urls:
            page_urls.append(page_id)
            seen_urls.add(page_id)

        next_page = clean_text((payload.get("next") or {}).get("id"))
        if not next_page or next_page in seen_urls:
            break
        payload = request_json(next_page)

    if not page_urls:
        raise ArtwallError("Rijksmuseum no ha devuelto paginas de coleccion.")

    save_cached_urls(RIJKS_PAGES_CACHE, page_urls)
    return page_urls


def load_recent_history() -> dict[str, list[int]]:
    if not HISTORY_PATH.exists():
        return {source: [] for source in SUPPORTED_MUSEUMS}

    try:
        payload = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {source: [] for source in SUPPORTED_MUSEUMS}

    history: dict[str, list[int]] = {source: [] for source in SUPPORTED_MUSEUMS}
    for source in SUPPORTED_MUSEUMS:
        entries = payload.get(source, [])
        history[source] = [int(object_id) for object_id in entries if isinstance(object_id, int)]
    return history


def save_recent_history(history: dict[str, list[int]]) -> None:
    payload = {source: history.get(source, []) for source in SUPPORTED_MUSEUMS}
    HISTORY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def remember_artwork(artwork: Artwork, *, limit: int = RECENT_HISTORY_SIZE) -> None:
    history = load_recent_history()
    source_history = [object_id for object_id in history.get(artwork.source, []) if object_id != artwork.object_id]
    source_history.append(artwork.object_id)
    history[artwork.source] = source_history[-max(1, limit):]
    save_recent_history(history)


def fetch_met_object_ids() -> list[int]:
    cached = load_cached_met_ids()
    if cached:
        return cached

    payload = request_json(
        MET_SEARCH_URL,
        params={
            "hasImages": "true",
            "q": "painting",
        },
    )
    object_ids = payload.get("objectIDs") or []
    if not object_ids:
        raise ArtwallError("The Met no ha devuelto obras con imagen.")

    filtered = [int(object_id) for object_id in object_ids if isinstance(object_id, int)]
    save_cached_met_ids(filtered)
    return filtered


def is_valid_met_object(payload: dict[str, Any]) -> bool:
    if not payload.get("isPublicDomain", False):
        return False
    if not (payload.get("primaryImage") or payload.get("primaryImageSmall")):
        return False

    classification = clean_text(payload.get("classification")).lower()
    object_name = clean_text(payload.get("objectName")).lower()
    medium = clean_text(payload.get("medium")).lower()
    keywords = f"{classification} {object_name} {medium}"
    return "painting" in keywords or "oil" in keywords or "canvas" in keywords


def choose_met_artwork() -> Artwork:
    object_ids = fetch_met_object_ids()
    sample_ids = random.sample(object_ids, min(len(object_ids), 40))
    checked = 0

    for object_id in sample_ids:
        checked += 1
        payload = request_json(MET_OBJECT_URL.format(object_id=object_id))
        if not is_valid_met_object(payload):
            continue

        title = clean_text(payload.get("title")) or "Sin titulo"
        author = clean_text(payload.get("artistDisplayName")) or "Autor desconocido"
        year = clean_text(payload.get("objectDate")) or "Fecha desconocida"
        image_url = payload.get("primaryImage") or payload.get("primaryImageSmall")
        object_url = payload.get("objectURL") or f"https://www.metmuseum.org/art/collection/search/{object_id}"
        log_selection_metrics("met", sampled=len(sample_ids), checked=checked, useful=1)
        return Artwork(
            source="met",
            object_id=int(object_id),
            title=title,
            author=author,
            year=year,
            image_url=image_url,
            page_url=object_url,
        )

    log_selection_metrics("met", sampled=len(sample_ids), checked=checked, useful=0)
    raise ArtwallError("No se encontro una obra valida en The Met tras varios intentos.")


def fetch_ngl_artwork_urls() -> list[str]:
    cached = load_cached_urls(NGL_URLS_CACHE, max_age_days=14)
    if cached:
        return cached

    response = requests.get(
        "https://www.nationalgallery.org.uk/xml-sitemap",
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    urls = re.findall(r"<loc>(https://www\.nationalgallery\.org\.uk/paintings/[^<]+)</loc>", response.text)
    if not urls:
        raise ArtwallError("National Gallery no ha devuelto URLs de obras.")

    save_cached_urls(NGL_URLS_CACHE, urls)
    return urls


def choose_ngl_artwork() -> Artwork:
    urls = fetch_ngl_artwork_urls()
    sample_urls = random.sample(urls, min(len(urls), 30))
    checked = 0

    for page_url in sample_urls:
        checked += 1
        response = requests.get(page_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        html = response.text

        thumbnail_match = re.search(r'<meta name="thumbnail" content="([^"]+)"', html)
        title_match = re.search(r"<title>([^<]+)</title>", html)
        description_match = re.search(r'<meta name="description" content="([^"]+)"', html)
        if not thumbnail_match or not title_match:
            continue

        image_url = thumbnail_match.group(1).replace("&amp;", "&")
        if image_url.startswith("/"):
            image_url = f"https://www.nationalgallery.org.uk{image_url}"

        title_parts = [part.strip() for part in title_match.group(1).split("|")]
        author = title_parts[0] if title_parts else "Autor desconocido"
        title = title_parts[1] if len(title_parts) > 1 else clean_slug_title(page_url)
        year = "Fecha desconocida"

        if description_match:
            description = description_match.group(1).replace("&amp;", "&")
            parts = description.split(". ", 1)[0].split(", ")
            if len(parts) >= 3:
                author = parts[0].strip() or author
                title = parts[1].strip() or title
                year = parts[2].strip() or year

        log_selection_metrics("ngl", sampled=len(sample_urls), checked=checked, useful=1)
        return Artwork(
            source="ngl",
            object_id=stable_object_id(page_url),
            title=clean_text(title),
            author=clean_text(author),
            year=clean_text(year),
            image_url=image_url,
            page_url=page_url,
        )

    log_selection_metrics("ngl", sampled=len(sample_urls), checked=checked, useful=0)
    raise ArtwallError("No se encontro una obra valida en National Gallery London.")


def fetch_cma_page(skip: int, limit: int) -> dict[str, Any]:
    return request_json(
        CMA_ARTWORKS_URL,
        params={
            "q": "painting",
            "has_image": 1,
            "cc0": 1,
            "limit": limit,
            "skip": skip,
        },
    )


def is_valid_cma_object(payload: dict[str, Any]) -> bool:
    if clean_text(payload.get("share_license_status")).upper() != "CC0":
        return False
    web_image_url = clean_text(((payload.get("images") or {}).get("web") or {}).get("url"))
    if not web_image_url:
        return False

    keywords = " ".join(
        [
            clean_text(payload.get("type")).lower(),
            clean_text(payload.get("title")).lower(),
        ]
    )
    return "painting" in keywords


def choose_cma_artwork() -> Artwork:
    first_page = fetch_cma_page(skip=0, limit=1)
    total = max(1, int((first_page.get("info") or {}).get("total", 1)))
    limit = 100
    max_skip = max(0, total - limit)
    total_candidates_seen = 0
    pages_checked = 0

    skips = {0}
    if max_skip > 0:
        extra_count = min(4, max(1, total // limit))
        for _ in range(extra_count):
            skips.add(random.randint(0, max_skip))

    for skip in random.sample(list(skips), len(skips)):
        pages_checked += 1
        payload = fetch_cma_page(skip=skip, limit=limit)
        candidates: list[Artwork] = []

        for item in payload.get("data") or []:
            if not is_valid_cma_object(item):
                continue

            image_url = clean_text(((item.get("images") or {}).get("web") or {}).get("url"))
            if not image_url:
                continue

            creators = item.get("creators") or []
            author = "Autor desconocido"
            if creators:
                primary = creators[0] or {}
                author = clean_text(primary.get("description")) or clean_text(primary.get("creator_description"))
            if author == "Autor desconocido":
                author = clean_text(item.get("culture")) or author

            candidates.append(
                Artwork(
                    source="cma",
                    object_id=int(item["id"]),
                    title=clean_text(item.get("title")) or "Sin titulo",
                    author=author,
                    year=clean_text(item.get("creation_date")) or "Fecha desconocida",
                    image_url=image_url,
                    page_url=clean_text(item.get("url")) or f"https://clevelandart.org/art/{item['id']}",
                )
            )

        total_candidates_seen += len(candidates)
        if candidates:
            log_selection_metrics(
                "cma",
                pages_checked=pages_checked,
                sampled_pages=len(skips),
                page_candidates=len(candidates),
                useful=total_candidates_seen,
            )
            return random.choice(candidates)

    log_selection_metrics("cma", pages_checked=pages_checked, sampled_pages=len(skips), useful=total_candidates_seen)
    raise ArtwallError("No se encontro una obra valida en Cleveland Museum of Art.")


def choose_rijks_artwork() -> Artwork:
    page_urls = fetch_rijks_page_urls()
    sample_page_urls = random.sample(page_urls, min(len(page_urls), 6))
    pages_checked = 0
    items_checked = 0

    for page_url in sample_page_urls:
        pages_checked += 1
        payload = request_json(page_url)
        ordered_items = payload.get("orderedItems") or []
        if not ordered_items:
            continue

        sample_items = random.sample(ordered_items, min(len(ordered_items), 20))
        for item in sample_items:
            items_checked += 1
            object_id_url = clean_text(item.get("id"))
            if not object_id_url:
                continue

            object_payload = request_json(object_id_url)
            page_candidates = (
                ((object_payload.get("subject_of") or [])[0].get("digitally_carried_by") or [])
                if object_payload.get("subject_of")
                else []
            )
            if not page_candidates:
                continue

            access_points = page_candidates[0].get("access_point") or []
            if not access_points:
                continue

            object_page_url = clean_text(access_points[0].get("id"))
            if not object_page_url:
                continue

            page_response = requests.get(object_page_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
            page_response.raise_for_status()
            image_url = extract_rijks_image_url(page_response.text)
            if not image_url:
                continue

            title = "Sin titulo"
            identified_by = object_payload.get("identified_by") or []
            for entry in identified_by:
                if entry.get("type") == "Name" and clean_text(entry.get("content")):
                    title = clean_text(entry.get("content"))
                    break

            author = "Autor desconocido"
            produced_by = object_payload.get("produced_by") or {}
            for part in produced_by.get("part") or []:
                carried_out_by = part.get("carried_out_by") or []
                if carried_out_by:
                    author = clean_text(((carried_out_by[0].get("notation") or [{}])[0]).get("@value")) or author
                    if author != "Autor desconocido":
                        break

            year = "Fecha desconocida"
            timespan = produced_by.get("timespan") or {}
            for entry in timespan.get("identified_by") or []:
                if entry.get("type") == "Name" and clean_text(entry.get("content")):
                    year = clean_text(entry.get("content"))
                    break

            log_selection_metrics(
                "rijks",
                page_pool=len(page_urls),
                sampled_pages=len(sample_page_urls),
                pages_checked=pages_checked,
                items_checked=items_checked,
                useful=1,
            )
            return Artwork(
                source="rijks",
                object_id=stable_object_id(object_id_url),
                title=title,
                author=author,
                year=year,
                image_url=image_url,
                page_url=object_page_url,
            )

    log_selection_metrics(
        "rijks",
        page_pool=len(page_urls),
        sampled_pages=len(sample_page_urls),
        pages_checked=pages_checked,
        items_checked=items_checked,
        useful=0,
    )
    raise ArtwallError("No se encontro una obra valida en Rijksmuseum.")


def extract_rijks_image_url(page_html: str) -> str | None:
    nuxt_payload_match = re.search(
        r'<script type="application/json" data-nuxt-data="nuxt-app" data-ssr="true" id="__NUXT_DATA__">(.*?)</script>',
        page_html,
        re.S,
    )
    if nuxt_payload_match:
        try:
            payload = json.loads(nuxt_payload_match.group(1))
            for entry in payload:
                if not isinstance(entry, dict) or "micrioImage" not in entry:
                    continue

                micrio_ref = entry.get("micrioImage")
                if not isinstance(micrio_ref, int) or not (0 <= micrio_ref < len(payload)):
                    continue

                micrio_image = payload[micrio_ref]
                if not isinstance(micrio_image, dict):
                    continue

                micrio_id_ref = micrio_image.get("micrioId")
                if not isinstance(micrio_id_ref, int) or not (0 <= micrio_id_ref < len(payload)):
                    continue

                micrio_id = payload[micrio_id_ref]
                if isinstance(micrio_id, str) and micrio_id:
                    return f"https://iiif.micr.io/{micrio_id}/full/max/0/default.jpg"
        except (ValueError, TypeError, IndexError, json.JSONDecodeError):
            pass

    image_match = re.search(r'<meta property="og:image" content="([^"]+)"', page_html)
    if image_match:
        return image_match.group(1).replace("&amp;", "&")
    return None


def choose_artwork_for_source(source: str) -> Artwork:
    if source == "met":
        return choose_met_artwork()
    if source == "cma":
        return choose_cma_artwork()
    if source == "ngl":
        return choose_ngl_artwork()
    if source == "rijks":
        return choose_rijks_artwork()
    raise ArtwallError(f"Fuente no soportada: {source}")


def choose_artwork(source: str) -> Artwork:
    chosen_source = normalize_source(source)
    recent_history = load_recent_history()
    candidate: Artwork | None = None
    recent_discards = 0
    attempts = 0

    if chosen_source == "random":
        for _ in range(RECENT_SELECTION_ATTEMPTS):
            attempts += 1
            museum = random.choice(list(SUPPORTED_MUSEUMS))
            candidate = choose_artwork_for_source(museum)
            if candidate.object_id not in recent_history.get(candidate.source, []):
                log_selection_metrics(
                    candidate.source,
                    requested=chosen_source,
                    attempts=attempts,
                    recent_discards=recent_discards,
                    recent_window=len(recent_history.get(candidate.source, [])),
                )
                return candidate
            recent_discards += 1

        if candidate is not None:
            log_selection_metrics(
                candidate.source,
                requested=chosen_source,
                attempts=attempts,
                recent_discards=recent_discards,
                recent_window=len(recent_history.get(candidate.source, [])),
                forced_recent=1,
            )
            return candidate
        raise ArtwallError("No se pudo elegir una obra aleatoria valida.")

    for _ in range(RECENT_SELECTION_ATTEMPTS):
        attempts += 1
        candidate = choose_artwork_for_source(chosen_source)
        if candidate.object_id not in recent_history.get(candidate.source, []):
            log_selection_metrics(
                candidate.source,
                requested=chosen_source,
                attempts=attempts,
                recent_discards=recent_discards,
                recent_window=len(recent_history.get(candidate.source, [])),
            )
            return candidate
        recent_discards += 1

    if candidate is not None:
        log_selection_metrics(
            candidate.source,
            requested=chosen_source,
            attempts=attempts,
            recent_discards=recent_discards,
            recent_window=len(recent_history.get(candidate.source, [])),
            forced_recent=1,
        )
        return candidate
    raise ArtwallError(f"Fuente no soportada: {source}")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        parts = [clean_text(item) for item in value]
        return " · ".join(part for part in parts if part)
    return " ".join(html.unescape(str(value)).split())


def clean_slug_title(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return slug.replace("-", " ").strip().title() or "Sin titulo"


def stable_object_id(value: str) -> int:
    return int(hashlib.sha1(value.encode("utf-8")).hexdigest()[:12], 16)


def download_artwork_image(artwork: Artwork) -> Path:
    extension = Path(artwork.image_url).suffix.lower() or ".jpg"
    target_path = CACHE_DIR / f"{artwork.source}-{artwork.object_id}{extension}"
    if target_path.exists():
        return target_path

    response = requests.get(artwork.image_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    target_path.write_bytes(response.content)
    return target_path


def detect_screen_size() -> tuple[int, int]:
    commands = [
        ["kscreen-doctor", "-o"],
        ["xrandr", "--current"],
    ]
    for command in commands:
        try:
            output = subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL)
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
        size = parse_screen_size(output)
        if size:
            return size
    return (1920, 1080)


def parse_screen_size(output: str) -> tuple[int, int] | None:
    for line in output.splitlines():
        for token in line.split():
            if "+" in token or "@" in token:
                candidate = token.split("@", 1)[0].split("+", 1)[0]
            else:
                candidate = token
            if "x" not in candidate:
                continue
            parts = candidate.lower().split("x", 1)
            if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
                continue
            width, height = int(parts[0]), int(parts[1])
            if width >= 800 and height >= 600:
                return (width, height)
    return None


def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_PATHS:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def wrap_line(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def render_wallpaper(image_path: Path, artwork: Artwork, width: int, height: int) -> Path:
    image = Image.open(image_path).convert("RGB")
    fitted = ImageOpsLike.contain_with_blurred_background(image, (width, height))

    overlay = Image.new("RGBA", fitted.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    museum_name = MUSEUM_LABELS.get(artwork.source, artwork.source)

    padding_x = max(10, width // 120)
    padding_y = max(8, height // 150)
    corner_radius = max(8, width // 220)
    title_font = get_font(max(12, width // 92))
    meta_font = get_font(max(9, width // 132))
    museum_font = get_font(max(9, width // 150))
    max_text_width = min(width // 4, width - padding_x * 2)

    title_lines = wrap_line(draw, artwork.title, title_font, max_text_width)
    meta_lines = wrap_line(draw, f"{artwork.author} · {artwork.year}", meta_font, max_text_width)
    museum_lines = wrap_line(draw, museum_name, museum_font, max_text_width)
    lines = (
        [(line, title_font, (245, 245, 240, 255)) for line in title_lines]
        + [(line, meta_font, (235, 235, 230, 255)) for line in meta_lines]
        + [(line, museum_font, (205, 205, 200, 210)) for line in museum_lines]
    )

    spacing = max(4, width // 420)
    line_heights = []
    for line, font, _color in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1])

    box_height = sum(line_heights) + spacing * (len(lines) - 1) + padding_y * 2
    box_width = max(int(draw.textlength(line, font=font)) for line, font, _color in lines) + padding_x * 2
    x0 = padding_x
    y0 = height - box_height - padding_x
    x1 = x0 + min(box_width, width - padding_x * 2)
    y1 = height - padding_x

    blur_layer = Image.new("RGBA", fitted.size, (0, 0, 0, 0))
    blur_draw = ImageDraw.Draw(blur_layer)
    blur_draw.rounded_rectangle((x0, y0, x1, y1), radius=corner_radius, fill=(0, 0, 0, 56))
    blur_layer = blur_layer.filter(ImageFilter.GaussianBlur(radius=3))
    overlay = Image.alpha_composite(overlay, blur_layer)

    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle((x0, y0, x1, y1), radius=corner_radius, fill=(18, 18, 18, 82))

    cursor_y = y0 + padding_y
    for index, (line, font, color) in enumerate(lines):
        draw.text((x0 + padding_x, cursor_y), line, font=font, fill=color)
        cursor_y += line_heights[index] + spacing

    composed = Image.alpha_composite(fitted.convert("RGBA"), overlay).convert("RGB")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = RENDER_DIR / f"{timestamp}-{artwork.source}-{artwork.object_id}.jpg"
    composed.save(output_path, format="JPEG", quality=92)
    return output_path


class ImageOpsLike:
    @staticmethod
    def cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
        target_w, target_h = size
        scale = max(target_w / image.width, target_h / image.height)
        resized = image.resize((int(image.width * scale), int(image.height * scale)), RESAMPLE_LANCZOS)
        left = max(0, (resized.width - target_w) // 2)
        top = max(0, (resized.height - target_h) // 2)
        return resized.crop((left, top, left + target_w, top + target_h))

    @staticmethod
    def contain_with_blurred_background(image: Image.Image, size: tuple[int, int]) -> Image.Image:
        target_w, target_h = size

        background = ImageOpsLike.cover(image, size).filter(ImageFilter.GaussianBlur(radius=18))
        dimmer = Image.new("RGB", size, (18, 18, 18))
        background = Image.blend(background.convert("RGB"), dimmer, alpha=0.28)

        scale = min(target_w / image.width, target_h / image.height)
        contained = image.resize(
            (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
            RESAMPLE_LANCZOS,
        )

        canvas = background.convert("RGBA")
        inset = max(0, min(target_w, target_h) // 60)
        contained_rgba = contained.convert("RGBA")
        shadow = Image.new(
            "RGBA",
            (contained_rgba.width + inset * 2, contained_rgba.height + inset * 2),
            (0, 0, 0, 0),
        )
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle(
            (inset, inset, shadow.width - inset, shadow.height - inset),
            radius=max(10, inset),
            fill=(0, 0, 0, 90),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(6, inset)))

        x = (target_w - contained.width) // 2
        y = (target_h - contained.height) // 2
        canvas.alpha_composite(shadow, (x - inset, y - inset))
        canvas.alpha_composite(contained_rgba, (x, y))
        return canvas.convert("RGB")


def apply_wallpaper_kde(image_path: Path) -> None:
    last_error: Exception | None = None

    for attempt in range(1, KDE_APPLY_RETRIES + 1):
        try:
            completed = subprocess.run(
                ["plasma-apply-wallpaperimage", str(image_path)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if completed.stderr.strip():
                message = f"[artwall] plasma-apply-wallpaperimage: {completed.stderr.strip()}"
                log_message(message)
                print(message, file=sys.stderr)
            return
        except FileNotFoundError as exc:
            log_message("[artwall] Error: no se encontro plasma-apply-wallpaperimage.")
            raise ArtwallError("No se encontro plasma-apply-wallpaperimage.") from exc
        except subprocess.CalledProcessError as exc:
            last_error = exc
            if attempt < KDE_APPLY_RETRIES:
                message = (
                    f"[artwall] Aviso: KDE rechazo el wallpaper, reintentando en "
                    f"{KDE_APPLY_RETRY_DELAY_SECONDS}s."
                )
                log_message(message)
                print(message, file=sys.stderr)
                time.sleep(KDE_APPLY_RETRY_DELAY_SECONDS)
                continue

    if isinstance(last_error, subprocess.CalledProcessError):
        stderr_text = (last_error.stderr or "").strip()
        details = f" (stderr: {stderr_text})" if stderr_text else ""
        log_message(
            f"[artwall] Error: KDE no ha aceptado el wallpaper tras {KDE_APPLY_RETRIES} "
            f"intento(s): codigo {last_error.returncode}{details}"
        )
        raise ArtwallError(
            f"KDE no ha aceptado el wallpaper tras {KDE_APPLY_RETRIES} intento(s): "
            f"codigo {last_error.returncode}{details}"
        ) from last_error
    log_message("[artwall] Error: no se pudo aplicar el wallpaper en KDE.")
    raise ArtwallError("No se pudo aplicar el wallpaper en KDE.")


def prune_rendered_files(keep_last: int) -> None:
    rendered_files = sorted(RENDER_DIR.glob("*.jpg"))
    excess = len(rendered_files) - keep_last
    for path in rendered_files[:max(0, excess)]:
        path.unlink(missing_ok=True)


def save_state(artwork: Artwork, rendered_path: Path, source_path: Path, size: tuple[int, int]) -> None:
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "artwork": asdict(artwork),
        "rendered_path": str(rendered_path),
        "source_path": str(source_path),
        "screen_size": {"width": size[0], "height": size[1]},
    }
    STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_wallpaper_cycle(settings: Settings, *, width: int = 0, height: int = 0) -> tuple[Artwork, Path]:
    ensure_dirs()

    target_width = width or settings.screen_width
    target_height = height or settings.screen_height
    if target_width <= 0 or target_height <= 0:
        target_width, target_height = detect_screen_size()

    artwork = choose_artwork(settings.source)
    source_path = download_artwork_image(artwork)
    rendered_path = render_wallpaper(source_path, artwork, target_width, target_height)
    apply_wallpaper_kde(rendered_path)
    prune_rendered_files(settings.keep_rendered)
    save_state(artwork, rendered_path, source_path, (target_width, target_height))
    remember_artwork(artwork)
    return artwork, rendered_path


def command_once(args: argparse.Namespace) -> None:
    settings = load_settings()
    artwork, rendered_path = run_wallpaper_cycle(settings, width=args.width, height=args.height)
    print(f"Wallpaper aplicado: {rendered_path}")
    print(f"{MUSEUM_LABELS.get(artwork.source, artwork.source)} | {artwork.author} | {artwork.title} | {artwork.year}")


def command_init(args: argparse.Namespace) -> None:
    ensure_dirs()
    settings = Settings(
        interval_minutes=max(1, args.minutes),
        source=normalize_source(args.source),
    )
    if CONFIG_PATH.exists():
        current = load_settings()
        settings.screen_width = current.screen_width
        settings.screen_height = current.screen_height
        settings.keep_rendered = current.keep_rendered
        settings.paused = current.paused
    save_settings(settings)
    print(f"Configuracion creada en {CONFIG_PATH}")


def build_systemd_units(minutes: int) -> tuple[str, str]:
    project_dir = Path(__file__).resolve().parent
    service = textwrap.dedent(
        f"""\
        [Unit]
        Description=artwall wallpaper rotator

        [Service]
        Type=oneshot
        WorkingDirectory={project_dir}
        ExecStart=/usr/bin/env python3 {project_dir / 'artwall.py'} once
        """
    )
    timer = textwrap.dedent(
        f"""\
        [Unit]
        Description=Run artwall every {minutes} minutes

        [Timer]
        OnBootSec=2min
        OnUnitActiveSec={minutes}min
        Unit=artwall.service

        [Install]
        WantedBy=timers.target
        """
    )
    return service, timer


def sync_systemd_timer_if_installed(minutes: int) -> None:
    user_systemd = Path.home() / ".config" / "systemd" / "user"
    service_path = user_systemd / "artwall.service"
    timer_path = user_systemd / "artwall.timer"
    if not service_path.exists() or not timer_path.exists():
        return

    service_text, timer_text = build_systemd_units(minutes)
    service_path.write_text(service_text, encoding="utf-8")
    timer_path.write_text(timer_text, encoding="utf-8")

    try:
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", "artwall.timer"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Aviso: no se pudo sincronizar el timer de systemd.", file=sys.stderr)


def command_install_systemd(args: argparse.Namespace) -> None:
    ensure_dirs()
    settings = load_settings()
    settings.interval_minutes = max(1, args.minutes)
    save_settings(settings)

    user_systemd = Path.home() / ".config" / "systemd" / "user"
    user_systemd.mkdir(parents=True, exist_ok=True)
    service_path = user_systemd / "artwall.service"
    timer_path = user_systemd / "artwall.timer"

    service_text, timer_text = build_systemd_units(settings.interval_minutes)
    service_path.write_text(service_text, encoding="utf-8")
    timer_path.write_text(timer_text, encoding="utf-8")

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "artwall.timer"], check=True)
    print(f"Instalado: {timer_path}")


def command_status() -> None:
    ensure_dirs()
    settings = load_settings()
    print(f"Config: {CONFIG_PATH}")
    print(f"Renderizados: {RENDER_DIR}")
    print(f"Intervalo: {settings.interval_minutes} minuto(s)")
    print(f"Museo: {MUSEUM_LABELS.get(settings.source, settings.source)}")
    print(f"Pausado: {'si' if settings.paused else 'no'}")
    if STATE_PATH.exists():
        print(STATE_PATH.read_text(encoding="utf-8"))
    else:
        print("Aun no hay una obra aplicada.")


class ArtwallTrayApp:
    def __init__(self) -> None:
        if not HAS_TRAY_SUPPORT or AppIndicator is None or GLib is None or Gtk is None:
            raise ArtwallError(
                "Faltan dependencias de bandeja. Instala python3-gi, gir1.2-gtk-3.0 y "
                "gir1.2-ayatanaappindicator3-0.1."
            )

        ensure_dirs()
        self.timer_id: int | None = None
        self.startup_timer_id: int | None = None
        self.interval_options = list(TRAY_INTERVAL_OPTIONS)
        self.interval_items: dict[int, Any] = {}
        self.source_items: dict[str, Any] = {}
        self.settings = load_settings()

        if self.settings.interval_minutes not in self.interval_options:
            self.settings.interval_minutes = 2
            save_settings(self.settings)

        self.indicator = AppIndicator.Indicator.new(
            APP_ID,
            ICON_NAME,
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_icon_theme_path(str(ICON_PATH.parent))
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title(APP_NAME)

        self.menu = self._build_menu()
        self.indicator.set_menu(self.menu)
        self._schedule_timer(run_now=False)
        self._schedule_startup_cycle()
        log_message("[artwall] Tray iniciado.")

    def _build_menu(self) -> Any:
        menu = Gtk.Menu()

        title_item = Gtk.MenuItem(label="artwall")
        title_item.set_sensitive(False)
        menu.append(title_item)

        menu.append(Gtk.SeparatorMenuItem())

        for minutes in self.interval_options:
            item = Gtk.CheckMenuItem(label=f"Cada {minutes} minuto(s)")
            item.connect("activate", self._on_set_interval, minutes)
            menu.append(item)
            self.interval_items[minutes] = item

        menu.append(Gtk.SeparatorMenuItem())

        for source_key in ("met", "cma", "ngl", "rijks", "random"):
            item = Gtk.CheckMenuItem(label=MUSEUM_LABELS[source_key])
            item.connect("activate", self._on_set_source, source_key)
            menu.append(item)
            self.source_items[source_key] = item

        menu.append(Gtk.SeparatorMenuItem())

        self.pause_item = Gtk.CheckMenuItem(label="Pausar")
        self.pause_item.set_active(self.settings.paused)
        self.pause_item.connect("toggled", self._on_toggle_pause)
        menu.append(self.pause_item)

        now_item = Gtk.MenuItem(label="Cambiar ahora")
        now_item.connect("activate", self._on_change_now)
        menu.append(now_item)

        open_item = Gtk.MenuItem(label="Abrir carpeta renderizada")
        open_item.connect("activate", self._on_open_folder)
        menu.append(open_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Salir")
        quit_item.connect("activate", self._on_quit)
        menu.append(quit_item)

        self._refresh_interval_checks()
        self._refresh_source_checks()
        menu.show_all()
        return menu

    def _refresh_interval_checks(self) -> None:
        for minutes, item in self.interval_items.items():
            item.set_active(minutes == self.settings.interval_minutes)

    def _refresh_source_checks(self) -> None:
        normalized = normalize_source(self.settings.source)
        for source_key, item in self.source_items.items():
            item.set_active(source_key == normalized)

    def _on_set_interval(self, item: Any, minutes: int) -> None:
        if not item.get_active():
            return
        self.settings.interval_minutes = minutes
        save_settings(self.settings)
        sync_systemd_timer_if_installed(minutes)
        self._refresh_interval_checks()
        self._schedule_timer(run_now=False)

    def _on_set_source(self, item: Any, source_key: str) -> None:
        if not item.get_active():
            return
        self.settings.source = source_key
        save_settings(self.settings)
        self._refresh_source_checks()

    def _on_toggle_pause(self, item: Any) -> None:
        self.settings.paused = item.get_active()
        save_settings(self.settings)
        self._schedule_timer(run_now=False)

    def _on_change_now(self, _item: Any) -> None:
        log_message("[artwall] Cambio manual solicitado desde la bandeja.")
        self._run_cycle()

    def _on_open_folder(self, _item: Any) -> None:
        subprocess.run(["xdg-open", str(RENDER_DIR)], check=False)

    def _on_quit(self, _item: Any) -> None:
        if self.timer_id is not None:
            GLib.source_remove(self.timer_id)
            self.timer_id = None
        if self.startup_timer_id is not None:
            GLib.source_remove(self.startup_timer_id)
            self.startup_timer_id = None
        log_message("[artwall] Tray detenido.")
        Gtk.main_quit()

    def _schedule_startup_cycle(self) -> None:
        if self.startup_timer_id is not None:
            GLib.source_remove(self.startup_timer_id)
            self.startup_timer_id = None
        if self.settings.paused:
            return
        self.startup_timer_id = GLib.timeout_add_seconds(TRAY_STARTUP_DELAY_SECONDS, self._on_startup_tick)

    def _schedule_timer(self, *, run_now: bool) -> None:
        if self.timer_id is not None:
            GLib.source_remove(self.timer_id)
            self.timer_id = None

        if self.settings.paused:
            return

        interval_seconds = max(60, self.settings.interval_minutes * 60)
        self.timer_id = GLib.timeout_add_seconds(interval_seconds, self._on_timer_tick)
        if run_now:
            self._run_cycle()

    def _on_startup_tick(self) -> bool:
        self.startup_timer_id = None
        if self.settings.paused:
            return False
        log_message("[artwall] Ejecutando primer cambio tras el arranque.")
        self._run_cycle()
        return False

    def _on_timer_tick(self) -> bool:
        if self.settings.paused:
            return True
        log_message("[artwall] Ejecutando cambio programado.")
        self._run_cycle()
        return True

    def _run_cycle(self) -> None:
        try:
            artwork, rendered_path = run_wallpaper_cycle(self.settings)
            message = (
                f"[artwall] {MUSEUM_LABELS.get(artwork.source, artwork.source)} | "
                f"{artwork.author} | {artwork.title} | {rendered_path}"
            )
            log_message(message)
            print(message)
        except (requests.RequestException, ArtwallError) as exc:
            message = f"[artwall] Error: {exc}"
            log_message(message)
            print(message, file=sys.stderr)
        except Exception as exc:
            message = f"[artwall] Error inesperado: {exc.__class__.__name__}: {exc}"
            log_message(message)
            log_message("[artwall] Traceback inesperado:\n" + traceback.format_exc().rstrip())
            print(message, file=sys.stderr)


def command_tray() -> None:
    load_tray_modules()
    ArtwallTrayApp()
    Gtk.main()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "once":
            command_once(args)
        elif args.command == "init":
            command_init(args)
        elif args.command == "install-systemd":
            command_install_systemd(args)
        elif args.command == "status":
            command_status()
        elif args.command == "tray":
            command_tray()
        else:
            raise ArtwallError(f"Comando no soportado: {args.command}")
        return 0
    except requests.RequestException as exc:
        print(f"Error de red: {exc}", file=sys.stderr)
        return 1
    except ArtwallError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
