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


def human_size(value, decimals=1, decimal_comma=False, compact_units=False):
    value = float(value or 0)
    units = ("B", "KB", "MB", "GB", "TB") if compact_units else ("B", "KiB", "MiB", "GiB", "TiB")
    for index, unit in enumerate(units):
        if value < 1024 or index == len(units) - 1:
            rendered = f"{value:.{decimals}f}"
            return f"{rendered.replace('.', ',') if decimal_comma else rendered} {unit}"
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


def torrent_actions(torrent, plex_available=False):
    from torrent_manager import supported_actions

    info_hash = torrent["hash"]
    actions = supported_actions(torrent)
    rows = []
    common = []
    if "refresh" in actions:
        common.append({"text": "🔄 Aggiorna", "callback_data": f"detail:{info_hash}"})
    common.append({"text": "ℹ️ Dettagli", "callback_data": f"detail:{info_hash}"})
    rows.append(common[:2])
    state_action = next((item for item in ("pause", "resume", "force", "retry") if item in actions), None)
    if state_action:
        labels = {
            "pause": "⏸ Pausa",
            "resume": "▶️ Riprendi",
            "force": "⏩ Forza avvio",
            "retry": "🔁 Riprova",
        }
        rows.append([{"text": labels[state_action], "callback_data": f"act:{state_action}:{info_hash}"}])
    if "completed_list" in actions:
        rows[0].append({"text": "📂 Altri completati", "callback_data": "list:completed:0"})
        if plex_available:
            rows.append([{"text": "🎬 Scansiona Plex", "callback_data": f"plex:{info_hash}"}])
    rows.append([{"text": "🗑 Gestisci rimozione", "callback_data": f"remove:{info_hash}"}])
    return {"inline_keyboard": rows}


def removal_menu(operation_id):
    return {
        "inline_keyboard": [
            [{"text": "🗑 Solo torrent", "callback_data": f"delete:keep:{operation_id}"}],
            [{"text": "⚠️ Torrent e file", "callback_data": f"delete:files:{operation_id}"}],
            [{"text": "↩️ Annulla", "callback_data": f"delete:cancel:{operation_id}"}],
        ]
    }


def final_delete_confirmation(operation_id):
    return {
        "inline_keyboard": [
            [{"text": "🔥 Conferma eliminazione", "callback_data": f"delete:confirm:{operation_id}"}],
            [{"text": "↩️ Annulla", "callback_data": f"delete:cancel:{operation_id}"}],
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
