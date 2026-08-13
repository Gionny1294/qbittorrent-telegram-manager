import base64
import hashlib
import re
import urllib.parse
from pathlib import PurePosixPath


class ValidationError(ValueError):
    pass


def magnet_hash(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value.strip())
    except ValueError as exc:
        raise ValidationError("Magnet URL non valido") from exc
    if parsed.scheme.lower() != "magnet":
        raise ValidationError("Il link non è un Magnet URL")
    xt_values = urllib.parse.parse_qs(parsed.query).get("xt", [])
    btih = next((item[9:] for item in xt_values if item.lower().startswith("urn:btih:")), "")
    if re.fullmatch(r"[0-9a-fA-F]{40}", btih):
        return btih.lower()
    if re.fullmatch(r"[A-Z2-7a-z2-7]{32}", btih):
        try:
            return base64.b32decode(btih.upper()).hex()
        except ValueError as exc:
            raise ValidationError("Hash Base32 del Magnet URL non valido") from exc
    raise ValidationError("Magnet URL privo di hash BitTorrent v1 valido")


def direct_torrent_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value.strip())
    except ValueError as exc:
        raise ValidationError("URL non valido") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValidationError("Sono ammessi soltanto URL HTTP/HTTPS")
    if not parsed.path.lower().endswith(".torrent"):
        raise ValidationError("L’URL deve puntare a un file .torrent")
    return value.strip()


def extract_input(text: str) -> tuple[str, str]:
    text = text.strip()
    if text.lower().startswith("magnet:?"):
        magnet_hash(text)
        return "magnet", text
    if text.lower().startswith(("http://", "https://")):
        return "url", direct_torrent_url(text)
    raise ValidationError("Invia un Magnet URL o un URL diretto a un file .torrent")


def _decode(data: bytes, offset: int = 0):
    if offset >= len(data):
        raise ValidationError("File .torrent incompleto")
    marker = data[offset : offset + 1]
    if marker == b"i":
        end = data.index(b"e", offset)
        return int(data[offset + 1 : end]), end + 1, (offset, end + 1)
    if marker == b"l":
        result, cursor = [], offset + 1
        while data[cursor : cursor + 1] != b"e":
            value, cursor, _ = _decode(data, cursor)
            result.append(value)
        return result, cursor + 1, (offset, cursor + 1)
    if marker == b"d":
        result, cursor = {}, offset + 1
        while data[cursor : cursor + 1] != b"e":
            key, cursor, _ = _decode(data, cursor)
            value, cursor, span = _decode(data, cursor)
            result[key] = (value, span)
        return result, cursor + 1, (offset, cursor + 1)
    colon = data.index(b":", offset)
    length = int(data[offset:colon])
    start, end = colon + 1, colon + 1 + length
    if end > len(data):
        raise ValidationError("File .torrent incompleto")
    return data[start:end], end, (offset, end)


def torrent_metadata(data: bytes) -> dict:
    try:
        root, end, _ = _decode(data)
        if end != len(data) or not isinstance(root, dict) or b"info" not in root:
            raise ValidationError("Metadati .torrent non validi")
        info, span = root[b"info"]
        name = info.get(b"name.utf-8", info.get(b"name", (b"Torrent", None)))[0]
        tracker = root.get(b"announce", (b"Non disponibile", None))[0]
        files = []
        if b"length" in info:
            size = int(info[b"length"][0])
            files = [name.decode("utf-8", "replace")]
        else:
            raw_files = info.get(b"files", ([], None))[0]
            size = sum(int(item[b"length"][0]) for item in raw_files)
            for item in raw_files:
                parts = item.get(b"path.utf-8", item.get(b"path", ([], None)))[0]
                files.append("/".join(part.decode("utf-8", "replace") for part in parts))
        return {
            # SHA-1 is mandated for BitTorrent v1 info-hashes, not used as a security primitive.
            "hash": hashlib.sha1(data[span[0] : span[1]], usedforsecurity=False).hexdigest(),
            "name": name.decode("utf-8", "replace"),
            "tracker": tracker.decode("utf-8", "replace"),
            "size": size,
            "files": files,
        }
    except (ValueError, IndexError, KeyError, TypeError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError("File .torrent non valido") from exc


def validate_files(files, blocked_patterns):
    for filename in files:
        normalized = filename.replace("\\", "/")
        parts = normalized.split("/")
        if normalized.startswith("/") or ".." in parts or any(not part for part in parts):
            raise ValidationError("Il torrent contiene un percorso non sicuro")
        lowered = normalized.lower()
        if any(pattern in lowered for pattern in blocked_patterns):
            raise ValidationError(f"File vietato rilevato: {filename}")


def sanitize_filename(filename):
    name = PurePosixPath(filename.replace("\\", "/")).name
    sanitized = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    if not sanitized or sanitized in {".", ".."}:
        raise ValidationError("Nome file non valido")
    return sanitized[:240]


def safe_destination(path, allowed_roots):
    import os

    resolved = os.path.realpath(path)
    if not any(
        resolved == os.path.realpath(root) or resolved.startswith(os.path.realpath(root) + os.sep)
        for root in allowed_roots
    ):
        raise ValidationError("Destinazione esterna alle cartelle consentite")
    return resolved
