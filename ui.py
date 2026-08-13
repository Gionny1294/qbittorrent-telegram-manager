CATEGORIES = {"film": "Film", "serie_tv": "Serie TV", "musica": "Musica", "altro": "Altro"}


def main_menu():
    return {
        "keyboard": [
            ["➕ Aggiungi", "⬇️ Attivi"],
            ["⏸ In pausa", "✅ Completati"],
            ["⚠️ Errori", "🔎 Cerca"],
            ["💾 Disco", "⚙️ Impostazioni"],
        ],
        "resize_keyboard": True,
    }


def category_keyboard(operation_id):
    return {
        "inline_keyboard": [
            [{"text": label, "callback_data": f"cat:{operation_id}:{key}"}]
            for key, label in CATEGORIES.items()
        ]
    }


def confirm_keyboard(operation_id):
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Conferma", "callback_data": f"confirm:{operation_id}"},
                {"text": "❌ Annulla", "callback_data": f"cancel:{operation_id}"},
            ]
        ]
    }


def human_size(value):
    value = float(value or 0)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024


def torrent_list_keyboard(items, group, page, pages):
    rows = [
        [
            {
                "text": f"{item.get('name', 'Torrent')[:45]} — {float(item.get('progress', 0)) * 100:.0f}%",
                "callback_data": f"detail:{item['hash']}",
            }
        ]
        for item in items
    ]
    navigation = []
    if page > 0:
        navigation.append({"text": "⬅️", "callback_data": f"list:{group}:{page - 1}"})
    navigation.append({"text": f"{page + 1}/{pages}", "callback_data": "noop"})
    if page + 1 < pages:
        navigation.append({"text": "➡️", "callback_data": f"list:{group}:{page + 1}"})
    rows.append(navigation)
    return {"inline_keyboard": rows}


def torrent_actions(info_hash):
    return {
        "inline_keyboard": [
            [{"text": "🔄 Aggiorna", "callback_data": f"detail:{info_hash}"}],
            [
                {"text": "⏸ Pausa", "callback_data": f"act:pause:{info_hash}"},
                {"text": "▶️ Riprendi", "callback_data": f"act:resume:{info_hash}"},
            ],
            [
                {"text": "⏩ Forza avvio", "callback_data": f"act:force:{info_hash}"},
                {"text": "🔁 Riprova", "callback_data": f"act:retry:{info_hash}"},
            ],
            [{"text": "🗑 Rimuovi torrent", "callback_data": f"delete:torrent:{info_hash}"}],
            [{"text": "🔥 Rimuovi torrent e file", "callback_data": f"delete:files1:{info_hash}"}],
            [{"text": "🎬 Scansiona Plex", "callback_data": f"plex:{info_hash}"}],
        ]
    }


def delete_confirmation(info_hash, with_files, second=False):
    kind = "files2" if with_files and second else "files1" if with_files else "torrent_confirm"
    return {
        "inline_keyboard": [
            [
                {"text": "Conferma eliminazione", "callback_data": f"delete:{kind}:{info_hash}"},
                {"text": "Annulla", "callback_data": f"detail:{info_hash}"},
            ]
        ]
    }


def settings_keyboard(queue_limit, mode):
    return {
        "inline_keyboard": [
            [
                {"text": f"Coda: {queue_limit}", "callback_data": "noop"},
                {"text": "➖", "callback_data": "setting:queue:-1"},
                {"text": "➕", "callback_data": "setting:queue:1"},
            ],
            [{"text": f"Modalità: {mode}", "callback_data": "setting:mode:toggle"}],
            [
                {"text": "Normale ↓", "callback_data": "setting:limits:normal_dl"},
                {"text": "Normale ↑", "callback_data": "setting:limits:normal_ul"},
            ],
            [
                {"text": "Notte ↓", "callback_data": "setting:limits:night_dl"},
                {"text": "Notte ↑", "callback_data": "setting:limits:night_ul"},
            ],
        ]
    }
