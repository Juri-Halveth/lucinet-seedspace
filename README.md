# LUCINET / SEEDSPACE

Interaktiver Browserraum für Juri Janovskis Kapselidee: **[Seedspace öffnen](https://juri-halveth.github.io/lucinet-seedspace/)**. Auf dem Handy beginnt er bildschirmfüllend mit einer einzigen Kugel. Jeder erste Wurf entfaltet eine Szene und schaltet die nächste Kugel frei:

1. Juri Janovski
2. Eines von drei Forschungsthemen
3. Die rote Stimme mit einem vom Ablageort abhängigen Mantra
4. Eine von drei grafischen Überraschungen
5. Juris Projektuniversum aus HALVETH, LUCINET, RED ROOM, Spielwelten und Connectoren

Nach der letzten Kugel bleiben alle fünf nutzbar. Bereits platzierte Szenen ruhen als leuchtende Punkte am eigenen Ort. Ein Klick auf einen Punkt öffnet seine Szene wieder. Ein erneuter Wurf desselben Typs entfernt seine alte Szene sofort und setzt sie an den neuen Ort.

## Wunschbrunnen nach Kugel fünf

Nach dem fünften Wurf kann man eigenen Text in eine **rote Kugel** schreiben. Das Schreiben allein startet noch keinen Generator und zeigt weder JSON noch Code. Die Kugel erscheint zuerst im Dock. Man muss sie greifen und im Raum ablegen; erst am Auftreffpunkt wird der Text analysiert und als benutzbare Szene entfaltet. Die Szene zeigt den eigenen Text, eine Suche und bei erkannten Aufgaben anklickbare Einträge.

Ein Knopf **in der entfalteten Szene** öffnet danach den getrennten Wunschprozess. Dort stehen Analyse, JSON-Ansicht, generierter Programmcode sowie JSON- und HTML-Download. Die Szene interpretiert denselben `seedspace.wish-program.v1`-Datensatz, der im JSON-Download steht und in die eigenständige HTML-Datei eingebettet ist. Der Browser verarbeitet nur die aktuelle Eingabe lokal. Das JSON enthält Originaltext, normalisierte Quelle, Fundstellen, gewählte Vorlage, offene Anschlüsse und den Quelltext der `index.html`. Die HTML-Datei kann auch direkt heruntergeladen werden. Eingaben werden nicht im Raumzustand gespeichert oder an eine API gesendet.

Der Generator baut vier tatsächlich implementierte Vorlagen: einen durchsuchbaren Leseraum für längere Texte und Kapitel, eine Aufgabenliste mit lokalem Abhaken und Hinzufügen, eine Zeitspur für datierte Texte oder einen durchsuchbaren Ideenatlas. Die Wahl entsteht aus sichtbaren lokalen Regeln; sie ist keine allgemeine Sprachmodell-Inferenz. Nicht implementierte Außenfunktionen wie API, Login, Datenbank oder Zahlung bleiben als offene Anschlüsse im JSON erhalten. Der vollständige Eingabetext bleibt erhalten, auch wenn eine Regel ihn nicht deuten kann.

Zahlungswörter einschließlich Überweisungsbitten, Ethereum und Wallet werden als offener Zahlungsanschluss ausgewiesen. Eine solche Bitte erzeugt nur einen lokalen Textentwurf und keine Transaktion oder Zustimmung Dritter.

Der kleine ↺-Knopf oben setzt alle lokalen Szenen und den aktuellen Wunschfortschritt zurück. Die Idee eines gemeinsamen Raums mit begrenzten, zeitlich belegten Plätzen steht separat in [PUBLIC_NOTEBOOK_CONCEPT.md](PUBLIC_NOTEBOOK_CONCEPT.md); diese Fassung enthält keine Zahlungsfunktion.

## Notizheft-Labor

Der [lokale Slot-Simulator](notebook-lab.html) setzt die Platzregeln als eigene Testfläche um: acht Plätze, begrenzte Radien und Abstände, kalendermonatliche Laufzeiten mit Nachfrist, freiwillige Verlängerung, Freigabe, lokales Archiv und JSON-Export. Er verwendet Browserdaten und Testeinträge; zwischen Besuchern findet kein Abgleich statt. Die angezeigten 1 BTC sind die Preisidee aus dem Konzept, kein Zahlungsangebot und keine Wallet-Verbindung.

## Start

`python -m http.server 8851 --bind 127.0.0.1` im Projektordner ausführen und [den lokalen Raum](http://127.0.0.1:8851/) öffnen. Das Projekt benötigt keine Build-Abhängigkeiten. Die veröffentlichte Fassung wird als statische Seite über GitHub Pages ausgeliefert.

## Bedienung und Daten

- Kugel greifen und im Raum loslassen; alternativ Kugel antippen und danach den Zielpunkt wählen.
- Die Telefonansicht nutzt die ganze Bildschirmhöhe. Szenen wachsen vom gewählten Punkt aus und passen ihre Richtung an den freien Platz an.
- Tastatur: Kugel wählen, Raum fokussieren, Enter oder Leertaste drücken.
- Das Symbol oben rechts öffnet die Szenenliste. Dort lassen sich Szenen aus- und einblenden oder die Geschichte neu beginnen.
- Die aktuelle Fassung verwendet den lokalen Schlüssel `lucinet.seedspace.room.v2`. Der frühere v1-Raum bleibt unter seinem bisherigen Schlüssel erhalten und wird nicht überschrieben.
- Die Stimme ist eine lokale, vorformulierte Szenenreaktion auf den Ablageort. Die Seite liest keine Cookies, Kamera oder Mikrofon und ruft im Betrieb keine externe API auf.

`blueprints.js` registriert die fünf Renderer; Daten werden nicht als fremder Code ausgeführt. `room-state.js` speichert Bauplan-ID, relative Position, Sichtbarkeit und Variantenindex. Die visuelle Browserfassung ist noch keine dreidimensionale Spielwelt.


## NOVA 2.1.0 · Research workbench

NOVA now has executable work controllers on top of the continuity core: source adapters, structure matching across names, countertests, portable analysis builds, optional local AI function generation and a value-flow inquiry. Start an offline demonstration in a fresh workspace:

```bash
python nova/nova.py --workspace ./nova-demo demo
```

The command prints a local HTML viewer and a verified continuation receipt. [Workbench guide](nova/WORKBENCH.md).

Version 2.1.0 also expands supplied source cards into quoted readings, compares
declared transitions, retains differences and countertests, and resumes the
resulting open questions. The [essence example](nova/examples/essence-nova-reviewed.json)
is a transparent analyst-authored comparison; optional local model results
remain separate. The 2.0.3 integrity and legacy-manifest checks are retained.

### Continuity core

This repository now also contains [`nova/`](nova/), a reusable Python runtime for provenance-preserving research continuity. It stores exact source bytes by SHA-256, keeps superseded/retracted interpretations searchable without treating them as current, writes hash-chained Research Receipts, verifies continuation state and exports portable research snapshots.

Quick start:

```bash
python nova/nova.py --version
python nova/nova.py --workspace ./my-research init --name my-research
python nova/nova.py --workspace ./my-research ingest ./notes
python nova/nova.py --workspace ./my-research search "what did we already research?"
python nova/nova.py --workspace ./my-research run "continue the current question" --mode FLOW --next-seed "next concrete test"
python nova/nova.py --workspace ./my-research verify
```

See [`nova/README.md`](nova/README.md) for the full contract, CLI, zero-install launchers and integration pattern.
