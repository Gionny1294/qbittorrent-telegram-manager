# Security policy

## Reporting

Do not disclose vulnerabilities in public issues. After publication, use GitHub's private vulnerability reporting feature or the private contact method configured by the repository owner. Do not include real tokens, Magnet URIs, torrent files or personal data in a report.

## Supported versions

Until the first release, only the latest default branch is supported. Security fixes should be applied to the newest release after versioning begins.

## Deployment guidance

- Keep Telegram, qBittorrent and Plex credentials outside Git.
- Restrict qBittorrent's Web UI to a private network and use dedicated credentials.
- Run the supplied non-root container and keep its read-only and capability restrictions.
- Mount media read-only into the bot; qBittorrent alone needs write access.
- Review logs and backups as sensitive operational data.
