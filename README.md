# ilias-sync-unimannheim

Inoffizielles Skript, das die Dateien deiner eigenen ILIAS-Kurse (Uni Mannheim, ILIAS 9) in einen lokalen Ordner herunterlädt.

- Login über Shibboleth/SAML2 (Uni-ID + Passwort), aufbauend auf dem Paket [IliasDownloaderUniMA](https://pypi.org/project/IliasDownloaderUniMA/).
- Nur Kurse (keine Gruppen), bestehende Dateien werden nie überschrieben.
- Videos und Dateien über `max_mb` werden übersprungen.
- Kurse werden über `mapping` in Zielordner einsortiert: `<Ordner>/ILIAS/<Kurs>/...`, der Rest landet in `Unsortiert/`.

## Voraussetzungen

- macOS (Passwort aus der Keychain; ohne Keychain gehen auch `ILIAS_PASSWORD` oder die Eingabe)
- Python 3.9+ und `pip install IliasDownloaderUniMA beautifulsoup4 lxml requests`

## Einrichtung

```sh
cp config.example.json config.json   # anpassen: target_dir, username, mapping
security add-generic-password -s ilias-unima -a <UNI-ID> -w   # fragt das Passwort ab
```

`config.json`:

| Schlüssel | Bedeutung |
|---|---|
| `target_dir` | Zielordner (`~` erlaubt) |
| `username` | Uni-ID |
| `keychain_service` | Keychain-Dienstname (Standard `ilias-unima`) |
| `mapping` | Teil des Kursnamens (Groß-/Kleinschreibung egal) -> Unterordner; erster Treffer gewinnt, spezifische Einträge zuerst |
| `ilias_subdir` / `unsorted_dir` | Namen der Unterordner |
| `skip` | Kurse mit diesen Namensteilen ignorieren |
| `own_groups` | optional: Kursname-Teil -> eigene Gruppennummer; Ordner `<n>. PG` anderer Gruppen werden übersprungen |
| `max_mb` | Größenlimit pro Datei |

Passwort-Reihenfolge: Keychain, dann Umgebungsvariable `ILIAS_PASSWORD`, dann Eingabeaufforderung.

## Ausführen

```sh
python3 ilias_sync.py --help
python3 ilias_sync.py            # nutzt ./config.json
python3 ilias_sync.py -c pfad/zu/config.json
```

## Täglich automatisch (optional)

`com.example.ilias-sync.plist` kopieren, Pfade (`/PFAD/ZU/...`) anpassen und laden:

```sh
cp com.example.ilias-sync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.example.ilias-sync.plist
```

Läuft dann täglich um 8:00 Uhr, Ausgabe in `sync.log`. Der Python-Pfad muss die Pakete oben enthalten (z. B. eine venv).

## Hinweise

- Inoffiziell, nicht mit der Universität Mannheim verbunden. Nutzung auf eigene Gefahr, ohne Gewährleistung.
- Nur für deine eigenen Kurse und deinen eigenen Account. Die ILIAS-Nutzungsbedingungen der Uni Mannheim sind einzuhalten; Materialien nicht weitergeben.
- Das Skript parst die ILIAS-Oberfläche und kann bei Änderungen an ILIAS oder am Login (z. B. MFA) brechen.
- `config.json`, Logs und Downloads sind per `.gitignore` ausgeschlossen. Nie Passwörter einchecken.

Lizenz: MIT
