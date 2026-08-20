import json
import os
import subprocess
from pathlib import Path


class MediaProcessingError(RuntimeError):
    pass


VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".ts", ".webm"}


def _inside(path, root):
    resolved, allowed = path.resolve(), root.resolve()
    return resolved == allowed or allowed in resolved.parents


def video_files(content_path, allowed_root):
    root = Path(allowed_root)
    content = Path(content_path)
    if not _inside(content, root):
        raise MediaProcessingError("Il percorso del torrent è esterno a disk4")
    candidates = [content] if content.is_file() else content.rglob("*")
    return sorted(
        item
        for item in candidates
        if item.is_file()
        and item.suffix.lower() in VIDEO_EXTENSIONS
        and not item.stem.endswith(".plex")
        and _inside(item, root)
    )


def _probe(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=index,codec_type:stream_tags=language", "-of", "json", str(path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return json.loads(result.stdout).get("streams", [])
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise MediaProcessingError(f"Impossibile analizzare {path.name}") from exc


def _is_italian(stream):
    language = str(stream.get("tags", {}).get("language", "")).lower().split("-", 1)[0]
    return language in {"it", "ita"}


def compress_video(source):
    streams = _probe(source)
    videos = [item for item in streams if item.get("codec_type") == "video"]
    audio = [item for item in streams if item.get("codec_type") == "audio"]
    if not videos:
        raise MediaProcessingError(f"{source.name} non contiene un flusso video")
    selected_audio = [item for item in audio if _is_italian(item)] or audio
    target = source.with_name(f"{source.stem}.plex.mp4")
    temporary = source.with_name(f".{source.stem}.compressing.mp4")
    command = [
        "ffmpeg", "-nostdin", "-y", "-i", str(source), "-map", f"0:{videos[0]['index']}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-threads", "1",
    ]
    for stream in selected_audio:
        command.extend(["-map", f"0:{stream['index']}"])
    if selected_audio:
        command.extend(["-c:a", "aac", "-b:a", "192k"])
    command.extend(["-movflags", "+faststart", str(temporary)])
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        if not temporary.is_file() or temporary.stat().st_size < 1024 or not _probe(temporary):
            raise MediaProcessingError(f"Verifica fallita per {source.name}")
        os.replace(temporary, target)
        source.unlink()
        return target, bool([item for item in audio if _is_italian(item)])
    except (OSError, subprocess.SubprocessError) as exc:
        raise MediaProcessingError(f"Compressione non riuscita per {source.name}") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
