# Bot Telegram per qBittorrent

Bot Telegram self-hosted, accessibile soltanto agli ID autorizzati, per aggiungere e gestire download qBittorrent. Supporta Magnet URI, URL diretti `.torrent` e file `.torrent`, con anteprima e conferma.

Distribuito con [licenza MIT](LICENSE).

## Funzioni

- allowlist Telegram, rate limiting e protezione dalle pressioni ripetute;
- categorie, cartelle, duplicati, spazio libero, limiti dimensionali e filtri;
- elenchi, ricerca, paginazione e schede dettagliate;
- pausa, ripresa, forza avvio, ricontrollo ed eliminazione confermata;
- notifiche persistenti, cronologia SQLite, coda e profili di velocità;
- notifiche di completamento compatte, pulsanti coerenti con lo stato e rimozione a conferma temporanea;
- stato server e integrazione Plex opzionale;
- container non-root, filesystem in sola lettura e healthcheck.

## Requisiti

- Docker con Compose v2 oppure Python 3.13;
- bot creato con [@BotFather](https://t.me/BotFather);
- Web API di qBittorrent raggiungibile;
- ID numerici Telegram degli utenti autorizzati.

Non sono necessarie dipendenze Python esterne in produzione.

## Screenshot

Segnaposto: prima della release aggiungere uno screenshot anonimizzato del menu, senza username, ID, nomi torrent o indirizzi server.

## Installazione Docker

```bash
git clone URL_DEL_REPOSITORY
cd NOME_REPOSITORY
cp .env.example .env
mkdir -p data logs downloads
chmod 600 .env
# Compilare .env prima di continuare.
docker compose config
docker compose up -d --build
docker compose ps
```

Log: `docker compose logs -f`. Arresto: `docker compose stop`.

## qBittorrent locale, Docker o remoto

- Sullo stesso host Docker: `QBITTORRENT_URL=http://host.docker.internal:8080`.
- In un altro container: collegare entrambi a una rete Docker comune e usare `http://qbittorrent:8080`.
- Su un altro server: usare un nome DNS o URL raggiungibile esclusivamente tramite rete privata/VPN.

Abilitare la Web UI, creare credenziali dedicate e limitarla alle reti fidate. Non esporla direttamente su Internet.

## BotFather e ID Telegram

Creare il bot tramite `@BotFather`, inserire il token in `TELEGRAM_BOT_TOKEN` e ottenere il proprio ID numerico tramite l'API Telegram o un bot ID affidabile. Inserire gli ID, separati da virgole, in `ALLOWED_USER_IDS`. Token e ID non devono essere committati.

## Configurazione `.env`

Il file `.env.example` descrive tutte le variabili. Sono obbligatorie:

- `TELEGRAM_BOT_TOKEN`;
- `ALLOWED_USER_IDS`;
- `QBITTORRENT_URL`;
- `DEFAULT_SAVE_PATH`.

Le credenziali qBittorrent sono necessarie quando l'autenticazione è abilitata. I percorsi categoria devono corrispondere a quelli visibili da qBittorrent. `MEDIA_ROOT_HOST` viene montato dal bot in sola lettura per misurare lo spazio.

Per Plex compilare `PLEX_URL`, `PLEX_TOKEN`, `PLEX_MOVIE_SECTION_ID` e `PLEX_SERIES_SECTION_ID`. Lasciando URL o token vuoti, Plex è disabilitato e il bot continua a funzionare.

`TITLE_MAX_LENGTH` limita il titolo mostrato nelle notifiche senza rinominare file o torrent. `DELETE_CONFIRMATION_SECONDS` stabilisce la durata delle conferme distruttive e `TZ` controlla l'orario locale visualizzato.

## Comandi

- `/start`: menu;
- `/help`: guida;
- `/status`: download attivi;
- `/downloads`: tutti i torrent attualmente in download;
- `/search nome`: ricerca;
- `/server`: stato qBittorrent, disco, RAM e carico;
- `/history`: cronologia operazioni.

## Installazione manuale e systemd

```bash
cp .env.example .env
mkdir -p data logs downloads
set -a
. ./.env
set +a
python3 bot.py
```

Per systemd adattare [systemd/qbittorrent-telegram.service](systemd/qbittorrent-telegram.service), installare il progetto in `/opt/qbittorrent-telegram` e la configurazione in `/etc/qbittorrent-telegram.env`:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now qbittorrent-telegram
sudo systemctl stop qbittorrent-telegram
sudo journalctl -u qbittorrent-telegram -f
```

## Backup e ripristino

```bash
docker compose exec -T bot python -c 'import sqlite3; s=sqlite3.connect("/app/data/bot.sqlite3"); d=sqlite3.connect("/app/data/backup.sqlite3"); s.backup(d); d.close(); s.close()'
```

Copiare `data/backup.sqlite3` in uno spazio protetto. Per ripristinare: fermare il bot, conservare il database corrente, copiare il backup come `data/bot.sqlite3`, correggere i permessi e riavviare.

## Aggiornamento e disinstallazione

```bash
docker compose build --pull
docker compose up -d
docker compose ps
```

Per rimuovere il servizio conservando i dati: `docker compose down`. Non cancellare `data/` senza backup e intenzione esplicita.

## Problemi comuni

- Il bot non risponde: verificare token, allowlist e log.
- qBittorrent non risponde: verificare URL, porta, firewall, rete Docker e credenziali.
- Container unhealthy: verificare i permessi di `data/` e `logs/`.
- Spazio errato: correggere `MEDIA_ROOT_HOST` e `DISK_CHECK_PATH`.
- Cartella errata: usare percorsi corrispondenti alla vista filesystem di qBittorrent.
- Plex non scansiona: controllare URL, token, sezioni e rete; l'errore non blocca i download.

## Sicurezza e uso responsabile

Proteggere `.env` con permessi `600`, usare credenziali dedicate, mantenere privata la Web UI e trattare log e backup come dati sensibili. Il software deve essere usato esclusivamente per contenuti che l'utente è legalmente autorizzato a scaricare e condividere.

Consultare [SECURITY.md](SECURITY.md), [CONTRIBUTING.md](CONTRIBUTING.md) e [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
