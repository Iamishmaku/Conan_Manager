import argparse
import json
import mimetypes
import os
import re
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

APP_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = APP_DIR / "settings.json"
DEFAULT_VIDEO_DIR = Path.home() / "Videos" / "Detective Conan"

def load_libraries():
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            libraries = data.get("libraries")
            if isinstance(libraries, list):
                result = []
                for item in libraries:
                    if isinstance(item, dict) and str(item.get("path", "")).strip():
                        result.append({"key": str(item.get("key") or f"raccolta-{len(result)+1}"), "label": str(item.get("label") or "Raccolta"), "kind": "movies" if item.get("kind") == "movies" else "episodes", "path": str(item["path"])})
                if result:
                    return result
            value = str(data.get("video_dir", "")).strip()
            if value:
                return [{"key": "1-1172", "label": "Episodi", "kind": "episodes", "path": value}]
        except Exception:
            pass
    return [{"key": "episodi", "label": "Episodi", "kind": "episodes", "path": str(DEFAULT_VIDEO_DIR)}]

LIBRARIES = load_libraries()
VIDEO_DIRS = {item["key"]: Path(item["path"]) for item in LIBRARIES}
LIBRARY_META = {item["key"]: item for item in LIBRARIES}
REFERENCE_PATH = APP_DIR / "reference.json"
LOG_PATH = APP_DIR / "rename_log.jsonl"
REGISTRY_PATH = APP_DIR / "file_registry.json"
CUSTOM_TITLES_PATH = APP_DIR / "custom_titles.json"
MISSING_TITLES_PATH = APP_DIR / "missing_titles.json"
TITLE_OVERRIDES_PATH = APP_DIR / "title_overrides.json"
WATCHED_PATH = APP_DIR / "watched.json"
PROGRESS_PATH = APP_DIR / "playback_progress.json"
TITLE_CARDS_PATH = APP_DIR / "title_cards.json"
ALLOWED_EXTENSIONS = {".mp4", ".mov"}
NAME_PATTERN = re.compile(r"^MeitanteiConan_Ep_(\d+)(.*?)_SUB_ITA$", re.IGNORECASE)
AUTO_NUMBER_PATTERNS = (
    re.compile(r"(?:^|[^a-z0-9])(?:ep|episodio|episode)[ _.-]*(\d{1,4})(?:[^0-9]|$)", re.IGNORECASE),
    re.compile(r"^(\d{1,4})(?:[ _.-]|$)", re.IGNORECASE),
)
MOVIE_NUMBER_PATTERN = re.compile(r"(?:film|movie|mov)[ _.-]*(\d{1,3})", re.IGNORECASE)
WPS_R133_TOKEN = "JAP_R133_INT_1134"
INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}

def load_reference():
    data = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    return {int(item["num_jap"]): item for item in data}

REFERENCE = load_reference()

def clean_title(value):
    return value.strip() if isinstance(value, str) else ""

def load_title_cards():
    if not TITLE_CARDS_PATH.exists():
        return {}
    try:
        return json.loads(TITLE_CARDS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

TITLE_CARDS = load_title_cards()

def save_title_cards(data):
    temporary = TITLE_CARDS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(TITLE_CARDS_PATH)

def registry_key(folder_key, filename):
    return f"{folder_key}|{filename}"

def relative_video_path(path, folder_key):
    return path.resolve().relative_to(VIDEO_DIRS[folder_key].resolve()).as_posix()

def resolve_video_path(folder_key, relative_path):
    if folder_key not in VIDEO_DIRS:
        raise ValueError("Cartella episodio non valida")
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("Percorso episodio non valido")
    relative = Path(relative_path.replace("/", os.sep))
    if relative.is_absolute():
        raise ValueError("Percorso episodio non valido")
    base = VIDEO_DIRS[folder_key].resolve()
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise ValueError("Percorso episodio non valido")
    return candidate

def recognize_number(stem):
    exact = NAME_PATTERN.match(stem)
    if exact:
        return int(exact.group(1)), exact, "nome standard"
    for pattern in AUTO_NUMBER_PATTERNS:
        match = pattern.search(stem)
        if match:
            return int(match.group(1)), None, "riconoscimento automatico"
    return None, None, ""

def load_registry():
    if not REGISTRY_PATH.exists():
        return {}
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        return {str(name): int(number) for name, number in data.items()}
    except Exception:
        return {}

def save_registry(data):
    temporary = REGISTRY_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(REGISTRY_PATH)

def load_custom_titles():
    if not CUSTOM_TITLES_PATH.exists():
        return {}
    try:
        data = json.loads(CUSTOM_TITLES_PATH.read_text(encoding="utf-8"))
        return {str(key): str(value) for key, value in data.items() if str(value).strip()}
    except Exception:
        return {}

def save_custom_titles(data):
    temporary = CUSTOM_TITLES_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(CUSTOM_TITLES_PATH)

def load_missing_titles():
    if not MISSING_TITLES_PATH.exists():
        return {}
    try:
        data = json.loads(MISSING_TITLES_PATH.read_text(encoding="utf-8"))
        return {str(key): str(value) for key, value in data.items() if str(value).strip()}
    except Exception:
        return {}

def save_missing_titles(data):
    temporary = MISSING_TITLES_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(MISSING_TITLES_PATH)

def load_title_overrides():
    data = {}
    if TITLE_OVERRIDES_PATH.exists():
        try:
            raw = json.loads(TITLE_OVERRIDES_PATH.read_text(encoding="utf-8"))
            missing_titles = load_missing_titles()
            for key, value in raw.items():
                if isinstance(value, dict):
                    key = str(key)
                    try:
                        number = int(key.rsplit("|", 1)[-1])
                    except (TypeError, ValueError):
                        continue
                    reference = REFERENCE.get(number, {})
                    reference_ita = clean_title(reference.get("name_ita"))
                    reference_eng = clean_title(reference.get("name_eng"))
                    reference_jap = clean_title(reference.get("name_jap"))
                    defaults = {
                        "name_ita": reference_ita or missing_titles.get(key, "") or TITLE_CARDS.get(str(number), {}).get("title_observed", ""),
                        "name_eng": reference_eng,
                        "name_jap": reference_jap,
                    }
                    overrides = {
                        field: str(value.get(field, "")).strip()
                        for field in ("name_ita", "name_eng", "name_jap")
                        if str(value.get(field, "")).strip() != str(defaults.get(field, "")).strip()
                    }
                    if any(overrides.values()):
                        data[key] = overrides
        except Exception:
            data = {}
    # Recupera eventuali titoli mancanti salvati dalla versione precedente.
    for key, title in load_missing_titles().items():
        data.setdefault(key, {"name_ita": "", "name_eng": "", "name_jap": ""})
        if not data[key]["name_ita"]:
            data[key]["name_ita"] = title
    return data

def save_title_overrides(data):
    temporary = TITLE_OVERRIDES_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(TITLE_OVERRIDES_PATH)

def load_watched():
    if not WATCHED_PATH.exists():
        return {}
    try:
        data = json.loads(WATCHED_PATH.read_text(encoding="utf-8"))
        return {str(key): str(value) for key, value in data.items() if str(value).strip()}
    except Exception:
        return {}

def save_watched(data):
    temporary = WATCHED_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(WATCHED_PATH)

def load_progress():
    if not PROGRESS_PATH.exists():
        return {}
    try:
        data = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        return {str(key): value for key, value in data.items() if isinstance(value, dict)}
    except Exception:
        return {}

def save_progress(data):
    temporary = PROGRESS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(PROGRESS_PATH)

def parse_file(path, folder_key, progress_data=None, media_index=None):
    registry = load_registry()
    relative_path = relative_video_path(path, folder_key)
    registered_number = registry.get(registry_key(folder_key, relative_path))
    if registered_number is None:
        registered_number = registry.get(registry_key(folder_key, path.name))
    if registered_number is None and folder_key == "1-1172":
        registered_number = registry.get(path.name)
    detected_number, match, recognition = recognize_number(path.stem)
    library = LIBRARY_META.get(folder_key, {})
    is_movie = library.get("kind") == "movies"
    if registered_number is None and detected_number is None and is_movie:
        movie_match = MOVIE_NUMBER_PATTERN.search(path.stem)
        detected_number = int(movie_match.group(1)) if movie_match else int(media_index or 1)
        recognition = "film riconosciuto"
    if registered_number is None and detected_number is None:
        return None
    is_wps_r133 = WPS_R133_TOKEN.lower() in path.stem.lower()
    number = registered_number if registered_number is not None else detected_number
    if registered_number is not None:
        recognition = "numero salvato"
    custom = match.group(2).strip(" _-") if match else ""
    ref = ({} if is_movie else ({
        "name_ita": "Police Academy Arc – Wild Police Story CASE. Rei Furuya",
        "name_eng": "Police Academy Arc Wild Police Story CASE. Rei Furuya",
        "name_jap": "警察学校編 Wild Police Story CASE. 降谷零",
        "num_ita": None,
        "anime_orig": False,
        "excel_row": 3837,
    } if is_wps_r133 else REFERENCE.get(number, {})))
    ref_ita = clean_title(ref.get("name_ita"))
    ref_eng = clean_title(ref.get("name_eng"))
    ref_jap = clean_title(ref.get("name_jap"))
    title_card = {} if is_movie else TITLE_CARDS.get(str(number), {})
    manual_title = load_custom_titles().get(f"{folder_key}|{number}", "")
    missing_title = load_missing_titles().get(f"{folder_key}|{number}", "")
    overrides = load_title_overrides().get(f"{folder_key}|{number}", {})
    override_ita = overrides.get("name_ita", "")
    override_eng = overrides.get("name_eng", "")
    override_jap = overrides.get("name_jap", "")
    watched_at = load_watched().get(f"{folder_key}|{number}", "")
    playback = (progress_data if progress_data is not None else load_progress()).get(registry_key(folder_key, relative_path), {})
    stat = path.stat()
    return {
        "number": number, "current_name": path.name, "relative_path": relative_path,
        "season_folder": path.parent.relative_to(VIDEO_DIRS[folder_key]).as_posix() if path.parent != VIDEO_DIRS[folder_key] else "",
        "recognition": recognition, "extension": path.suffix.lower(),
        "display_number": (f"FILM {number}" if is_movie else ("R133" if is_wps_r133 else str(number))),
        "num_int": 1134 if is_wps_r133 else None,
        "is_special": is_wps_r133, "is_movie": is_movie,
        "custom_title": custom, "duration": None, "size": stat.st_size,
        "modified_ns": stat.st_mtime_ns, "folder_key": folder_key,
        "folder_path": str(VIDEO_DIRS[folder_key]), "folder_label": library.get("label", folder_key),
        "name_ita": override_ita or missing_title or ref_ita or title_card.get("title_observed", "") or (path.stem.replace("_", " ") if is_movie else ""),
        "name_eng": override_eng or ref_eng,
        "name_jap": override_jap or ref_jap,
        "excel_name_ita": ref_ita, "excel_name_eng": ref_eng,
        "excel_name_jap": ref_jap, "manual_title": manual_title,
        "missing_title": missing_title, "title_overrides": overrides,
        "watched": bool(watched_at), "watched_at": watched_at,
        "playback": playback,
        "title_card_url": f"/title_cards/{title_card['file']}" if title_card.get("file") else "",
        "title_card_observed": title_card.get("title_observed", ""),
        "title_card_certainty": title_card.get("certainty", ""),
        "title_card_time": title_card.get("time_label", ""),
        "num_ita": ref.get("num_ita"),
        "anime_orig": bool(ref.get("anime_orig")), "excel_row": ref.get("excel_row"), "library_kind": library.get("kind", "episodes"),
    }

def inventory():
    # Rilegge i dati di riferimento a ogni aggiornamento della pagina, così i
    # nuovi titoli compaiono subito senza dover chiudere e riavviare il server.
    global REFERENCE, TITLE_CARDS
    REFERENCE = load_reference()
    TITLE_CARDS = load_title_cards()
    records, unrecognized, folders = [], [], []
    progress_data = load_progress()
    for folder_key, video_dir in VIDEO_DIRS.items():
        if not video_dir.is_dir():
            meta = LIBRARY_META.get(folder_key, {})
            folders.append({"key": folder_key, "label": meta.get("label", folder_key), "kind": meta.get("kind", "episodes"), "path": str(video_dir), "count": 0, "error": "Cartella non trovata"})
            continue
        folder_count = 0
        video_paths = sorted(
            (path for path in video_dir.rglob("*") if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS),
            key=lambda item: item.relative_to(video_dir).as_posix().lower(),
        )
        for media_index, path in enumerate(video_paths, 1):
            folder_count += 1
            record = parse_file(path, folder_key, progress_data, media_index)
            if record:
                records.append(record)
            else:
                unrecognized.append({"folder_key": folder_key, "name": path.relative_to(video_dir).as_posix()})
        meta = LIBRARY_META.get(folder_key, {})
        folders.append({"key": folder_key, "label": meta.get("label", folder_key), "kind": meta.get("kind", "episodes"), "path": str(video_dir), "count": folder_count, "error": None})
    records.sort(key=lambda item: (item["number"], item["folder_key"], item["current_name"].lower()))
    resumable = [item for item in records if item.get("playback", {}).get("position", 0) > 0 and not item.get("playback", {}).get("completed")]
    last_progress = max(resumable, key=lambda item: item.get("playback", {}).get("updated_at", ""), default=None)
    return {
        "folders": folders, "records": records, "unrecognized": unrecognized,
        "last_progress": last_progress,
        "counts": {
            "files": len(records), "mp4": sum(item["extension"] == ".mp4" for item in records),
            "mov": sum(item["extension"] == ".mov" for item in records),
            "anime_orig": sum(item["anime_orig"] for item in records),
            "watched": sum(item["watched"] for item in records),
            "in_progress": len(resumable),
        },
    }

def save_libraries():
    temporary = SETTINGS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps({"libraries": LIBRARIES}, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(SETTINGS_PATH)

def add_video_folder(path_value, kind="episodes", label=""):
    global LIBRARIES, VIDEO_DIRS, LIBRARY_META
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError("Scegli una cartella valida")
    path = Path(path_value.strip()).expanduser()
    if not path.is_dir():
        raise FileNotFoundError(f"Cartella non trovata: {path}")
    path = path.resolve()
    if not SETTINGS_PATH.exists() and len(LIBRARIES) == 1 and not Path(LIBRARIES[0]["path"]).is_dir():
        LIBRARIES = []; VIDEO_DIRS = {}; LIBRARY_META = {}
    kind = "movies" if kind == "movies" else "episodes"
    for item in LIBRARIES:
        if Path(item["path"]).resolve() == path:
            raise ValueError("Questa cartella è già presente")
    base = "film" if kind == "movies" else "episodi"
    used = {item["key"] for item in LIBRARIES}
    index, key = 1, base
    while key in used:
        index += 1; key = f"{base}-{index}"
    item = {"key": key, "label": (str(label).strip() or ("Film" if kind == "movies" else "Episodi")), "kind": kind, "path": str(path)}
    LIBRARIES.append(item); VIDEO_DIRS[key] = path; LIBRARY_META[key] = item; save_libraries()
    result = inventory()
    return {"ok": True, "library": item, "path": str(path), "count": result["counts"]["files"], "unrecognized": len(result["unrecognized"])}

def remove_video_folder(key):
    global LIBRARIES, VIDEO_DIRS, LIBRARY_META
    if key not in VIDEO_DIRS:
        raise ValueError("Raccolta non trovata")
    LIBRARIES = [item for item in LIBRARIES if item["key"] != key]
    VIDEO_DIRS.pop(key, None); LIBRARY_META.pop(key, None); save_libraries()
    return {"ok": True}

def choose_video_folder():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            parent=root,
            title="Scegli la cartella degli episodi di Detective Conan",
            initialdir=str(next((path for path in VIDEO_DIRS.values() if path.is_dir()), DEFAULT_VIDEO_DIR.parent)),
            mustexist=True,
        )
    finally:
        root.destroy()
    if not selected:
        return {"ok": False, "cancelled": True}
    return {"ok": True, "path": selected}

def validate_new_name(current_name, new_name):
    if not isinstance(current_name, str) or not isinstance(new_name, str):
        raise ValueError("Nome non valido")
    if Path(current_name).name != current_name or Path(new_name).name != new_name:
        raise ValueError("Sono ammessi soltanto nomi di file, senza percorsi")
    new_name = new_name.strip()
    if not new_name or len(new_name) > 240:
        raise ValueError("Il nuovo nome e vuoto o troppo lungo")
    if INVALID_CHARS.search(new_name) or new_name.endswith((" ", ".")):
        raise ValueError("Il nuovo nome contiene caratteri non ammessi da Windows")
    if Path(new_name).stem.upper() in RESERVED:
        raise ValueError("Nome riservato da Windows")
    current_ext, new_ext = Path(current_name).suffix.lower(), Path(new_name).suffix.lower()
    if current_ext not in ALLOWED_EXTENSIONS or new_ext != current_ext:
        raise ValueError("L'estensione del video non puo essere modificata")
    return new_name

def rename_file(payload):
    if payload.get("confirm") is not True:
        raise ValueError("Conferma mancante")
    folder_key = payload.get("folder_key")
    if folder_key not in VIDEO_DIRS:
        raise ValueError("Cartella episodio non valida")
    video_dir = VIDEO_DIRS[folder_key]
    current_name = payload.get("current_name")
    new_name = validate_new_name(current_name, payload.get("new_name"))
    relative_path = payload.get("relative_path") or current_name
    source = resolve_video_path(folder_key, relative_path)
    target = source.with_name(new_name)
    if not source.is_file():
        raise FileNotFoundError(f"File non trovato: {current_name}")
    source_record = parse_file(source, folder_key)
    if source_record is None:
        raise ValueError("Nome episodio non riconosciuto")
    if target.exists() and source.resolve() != target.resolve():
        raise FileExistsError(f"Esiste gia: {new_name}")
    before, renamed = source.stat(), source.name != target.name
    if renamed:
        source.rename(target)
    registry = load_registry()
    registry.pop(registry_key(folder_key, relative_path), None)
    registry.pop(registry_key(folder_key, current_name), None)
    if folder_key == "1-1172":
        registry.pop(current_name, None)
    new_relative_path = target.resolve().relative_to(video_dir.resolve()).as_posix()
    registry[registry_key(folder_key, new_relative_path)] = source_record["number"]
    try:
        save_registry(registry)
    except Exception:
        if renamed and target.exists() and not source.exists():
            target.rename(source)
        raise
    after = target.stat()
    if before.st_size != after.st_size:
        raise RuntimeError("La dimensione del file e cambiata inaspettatamente")
    log = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "folder_key": folder_key, "folder": str(video_dir), "old": current_name,
        "new": new_name, "size": after.st_size,
    }
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(log, ensure_ascii=False) + "\n")
    return {"ok": True, "record": parse_file(target, folder_key), "log": log}

def save_manual_title(payload):
    folder_key = payload.get("folder_key")
    number = payload.get("number")
    title = payload.get("title")
    if folder_key not in VIDEO_DIRS:
        raise ValueError("Cartella episodio non valida")
    if not isinstance(number, int) or number < 1 or number > 9999:
        raise ValueError("Numero episodio non valido")
    if not isinstance(title, str):
        raise ValueError("Titolo non valido")
    title = title.strip()
    if len(title) > 240 or any(ord(char) < 32 for char in title):
        raise ValueError("Il titolo e troppo lungo o contiene caratteri non validi")
    data = load_custom_titles()
    key = f"{folder_key}|{number}"
    if title:
        data[key] = title
    else:
        data.pop(key, None)
    save_custom_titles(data)
    return {"ok": True, "folder_key": folder_key, "number": number, "title": title}

def save_missing_title(payload):
    folder_key = payload.get("folder_key")
    number = payload.get("number")
    title = payload.get("title")
    if folder_key not in VIDEO_DIRS:
        raise ValueError("Cartella episodio non valida")
    if not isinstance(number, int) or number < 1 or number > 9999:
        raise ValueError("Numero episodio non valido")
    if not isinstance(title, str):
        raise ValueError("Titolo non valido")
    ref = REFERENCE.get(number, {})
    if ref.get("name_ita") or ref.get("name_eng") or ref.get("name_jap"):
        raise ValueError("Questo episodio ha gia un titolo nel riferimento Excel")
    title = title.strip()
    if len(title) > 240 or any(ord(char) < 32 for char in title):
        raise ValueError("Il titolo e troppo lungo o contiene caratteri non validi")
    data = load_missing_titles()
    key = f"{folder_key}|{number}"
    if title:
        data[key] = title
    else:
        data.pop(key, None)
    save_missing_titles(data)
    return {"ok": True, "folder_key": folder_key, "number": number, "title": title}

def save_reference_titles(payload):
    folder_key = payload.get("folder_key")
    number = payload.get("number")
    if folder_key not in VIDEO_DIRS:
        raise ValueError("Cartella episodio non valida")
    if not isinstance(number, int) or number < 1 or number > 9999:
        raise ValueError("Numero episodio non valido")
    values = {}
    for field in ("name_ita", "name_eng", "name_jap"):
        value = payload.get(field, "")
        if not isinstance(value, str):
            raise ValueError("Titolo non valido")
        value = value.strip()
        if len(value) > 240 or any(ord(char) < 32 for char in value):
            raise ValueError("Un titolo e troppo lungo o contiene caratteri non validi")
        values[field] = value
    key = f"{folder_key}|{number}"
    reference = REFERENCE.get(number, {})
    reference_ita = clean_title(reference.get("name_ita"))
    reference_eng = clean_title(reference.get("name_eng"))
    reference_jap = clean_title(reference.get("name_jap"))
    defaults = {
        "name_ita": reference_ita or load_missing_titles().get(key, "") or TITLE_CARDS.get(str(number), {}).get("title_observed", ""),
        "name_eng": reference_eng,
        "name_jap": reference_jap,
    }
    overrides = {
        field: value
        for field, value in values.items()
        if value and value != str(defaults.get(field, "")).strip()
    }
    data = load_title_overrides()
    if any(overrides.values()):
        data[key] = overrides
    else:
        data.pop(key, None)
    save_title_overrides(data)
    return {"ok": True, "folder_key": folder_key, "number": number, "titles": overrides}

def set_watched(payload):
    folder_key = payload.get("folder_key")
    number = payload.get("number")
    watched = payload.get("watched")
    if folder_key not in VIDEO_DIRS:
        raise ValueError("Cartella episodio non valida")
    if not isinstance(number, int) or number < 1 or number > 9999:
        raise ValueError("Numero episodio non valido")
    if not isinstance(watched, bool):
        raise ValueError("Stato visto non valido")
    data = load_watched()
    key = f"{folder_key}|{number}"
    watched_at = datetime.now().astimezone().isoformat(timespec="seconds") if watched else ""
    if watched:
        data[key] = watched_at
    else:
        data.pop(key, None)
    save_watched(data)
    return {"ok": True, "folder_key": folder_key, "number": number, "watched": watched, "watched_at": watched_at}

def set_progress(payload):
    folder_key = payload.get("folder_key")
    relative_path = payload.get("relative_path")
    number = payload.get("number")
    if folder_key not in VIDEO_DIRS or not isinstance(number, int):
        raise ValueError("Episodio non valido")
    path = resolve_video_path(folder_key, relative_path)
    if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise FileNotFoundError("Video non trovato")
    try:
        position = max(0.0, float(payload.get("position", 0)))
        duration = max(0.0, float(payload.get("duration", 0)))
    except (TypeError, ValueError):
        raise ValueError("Tempo di riproduzione non valido")
    if position != position or duration != duration or position > 86400 or duration > 86400:
        raise ValueError("Tempo di riproduzione non valido")
    completed = bool(payload.get("completed")) or (duration > 0 and position >= duration - 15)
    if completed and duration:
        position = duration
    item = {
        "number": number, "position": round(position, 2), "duration": round(duration, 2),
        "completed": completed, "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    data = load_progress()
    data[registry_key(folder_key, relative_video_path(path, folder_key))] = item
    save_progress(data)
    if completed:
        set_watched({"folder_key": folder_key, "number": number, "watched": True})
    return {"ok": True, "playback": item}

def play_file(payload):
    folder_key = payload.get("folder_key")
    current_name = payload.get("current_name")
    number = payload.get("number")
    if folder_key not in VIDEO_DIRS:
        raise ValueError("Cartella episodio non valida")
    if not isinstance(current_name, str) or Path(current_name).name != current_name:
        raise ValueError("Nome file non valido")
    if not isinstance(number, int) or number < 1 or number > 9999:
        raise ValueError("Numero episodio non valido")
    path = resolve_video_path(folder_key, payload.get("relative_path") or current_name)
    if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise FileNotFoundError(f"File non trovato: {current_name}")
    os.startfile(str(path))
    return set_watched({"folder_key": folder_key, "number": number, "watched": True})

def change_episode_number(payload):
    folder_key = payload.get("folder_key")
    current_name = payload.get("current_name")
    old_number = payload.get("old_number")
    new_number = payload.get("new_number")
    if folder_key not in VIDEO_DIRS:
        raise ValueError("Cartella episodio non valida")
    if not isinstance(current_name, str) or Path(current_name).name != current_name:
        raise ValueError("Nome file non valido")
    if not isinstance(old_number, int) or not isinstance(new_number, int) or not 1 <= new_number <= 9999:
        raise ValueError("Numero JAP non valido")
    relative_path = payload.get("relative_path") or current_name
    source = resolve_video_path(folder_key, relative_path)
    if not source.is_file():
        raise FileNotFoundError(f"File non trovato: {current_name}")
    current_record = parse_file(source, folder_key)
    if current_record is None or current_record["number"] != old_number:
        raise ValueError("L'identita corrente dell'episodio non corrisponde")
    if new_number == old_number:
        return {"ok": True, "record": current_record}
    for candidate in VIDEO_DIRS[folder_key].rglob("*"):
        if candidate == source or not candidate.is_file() or candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        candidate_record = parse_file(candidate, folder_key)
        if candidate_record and candidate_record["number"] == new_number:
            raise FileExistsError(f"Esiste gia un altro file associato al JAP {new_number}: {candidate.name}")
    old_key = f"{folder_key}|{old_number}"
    new_key = f"{folder_key}|{new_number}"
    stores = [
        (load_custom_titles, save_custom_titles),
        (load_missing_titles, save_missing_titles),
        (load_title_overrides, save_title_overrides),
        (load_watched, save_watched),
    ]
    for loader, saver in stores:
        data = loader()
        if old_key in data:
            data[new_key] = data.pop(old_key)
            saver(data)
    old_card, new_card = str(old_number), str(new_number)
    if old_card in TITLE_CARDS:
        TITLE_CARDS[new_card] = TITLE_CARDS.pop(old_card)
        save_title_cards(TITLE_CARDS)
    registry = load_registry()
    registry.pop(registry_key(folder_key, relative_path), None)
    registry.pop(registry_key(folder_key, current_name), None)
    if folder_key == "1-1172":
        registry.pop(current_name, None)
    registry[registry_key(folder_key, relative_video_path(source, folder_key))] = new_number
    save_registry(registry)
    return {"ok": True, "record": parse_file(source, folder_key)}

class Handler(BaseHTTPRequestHandler):
    server_version = "ConanManager/2.0"
    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/episodes":
            try:
                self.send_json(200, inventory())
            except Exception as error:
                self.send_json(500, {"error": str(error)})
            return
        if parsed.path == "/api/media":
            try:
                query = parse_qs(parsed.query)
                folder_key = query.get("folder_key", [""])[0]
                relative_path = query.get("path", [""])[0]
                candidate = resolve_video_path(folder_key, relative_path)
                if not candidate.is_file() or candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
                    raise FileNotFoundError("Video non trovato")
                size = candidate.stat().st_size
                start, end, status = 0, size - 1, 200
                range_header = self.headers.get("Range", "")
                if range_header:
                    match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
                    if not match:
                        self.send_error(416)
                        return
                    first, last = match.groups()
                    if first:
                        start = int(first)
                        end = min(int(last), size - 1) if last else size - 1
                    elif last:
                        start = max(0, size - int(last))
                    if start >= size or end < start:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.end_headers()
                        return
                    status = 206
                length = end - start + 1
                self.send_response(status)
                self.send_header("Content-Type", mimetypes.guess_type(candidate.name)[0] or "video/mp4")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(length))
                if status == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                with candidate.open("rb") as handle:
                    handle.seek(start)
                    remaining = length
                    while remaining:
                        chunk = handle.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except (ValueError, FileNotFoundError) as error:
                self.send_error(404, str(error))
            return
        relative = unquote(parsed.path.lstrip("/")) or "index.html"
        candidate = (APP_DIR / relative).resolve()
        try:
            candidate.relative_to(APP_DIR)
        except ValueError:
            self.send_error(403)
            return
        if not candidate.is_file():
            self.send_error(404)
            return
        content = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)
    def do_POST(self):
        endpoint = urlparse(self.path).path
        if endpoint not in {"/api/rename", "/api/title", "/api/missing-title", "/api/reference-titles", "/api/watched", "/api/progress", "/api/episode-number", "/api/select-folder", "/api/video-folder", "/api/remove-folder"}:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 32768:
                raise ValueError("Richiesta non valida")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if endpoint == "/api/select-folder":
                result = choose_video_folder()
            elif endpoint == "/api/video-folder":
                result = add_video_folder(payload.get("path"), payload.get("kind"), payload.get("label"))
            elif endpoint == "/api/remove-folder":
                result = remove_video_folder(payload.get("key"))
            elif endpoint == "/api/rename":
                result = rename_file(payload)
            elif endpoint == "/api/missing-title":
                result = save_missing_title(payload)
            elif endpoint == "/api/reference-titles":
                result = save_reference_titles(payload)
            elif endpoint == "/api/watched":
                result = set_watched(payload)
            elif endpoint == "/api/progress":
                result = set_progress(payload)
            elif endpoint == "/api/episode-number":
                result = change_episode_number(payload)
            else:
                result = save_manual_title(payload)
            self.send_json(200, result)
        except FileExistsError as error:
            self.send_json(409, {"error": str(error)})
        except (ValueError, FileNotFoundError) as error:
            self.send_json(400, {"error": str(error)})
        except Exception as error:
            self.send_json(500, {"error": str(error)})
    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Conan Manager disponibile su {url}", flush=True)
    for folder_key, path in VIDEO_DIRS.items():
        print(f"Blocco {folder_key}: {path}", flush=True)
    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(0.8), webbrowser.open(url)), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
