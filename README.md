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

Ein Knopf **in der entfalteten Szene** öffnet danach den getrennten Wunschprozess. Dort stehen Analyse, JSON-Ansicht, generierter Programmcode sowie JSON- und HTML-Download. Der Browser verarbeitet nur die aktuelle Eingabe lokal. Das JSON enthält Originaltext, normalisierte Quelle, Fundstellen, gewählte Vorlage, offene Anschlüsse und den Quelltext einer eigenständigen `index.html`. Die HTML-Datei kann auch direkt heruntergeladen werden. Eingaben werden nicht im Raumzustand gespeichert oder an eine API gesendet.

Der Generator baut vier tatsächlich implementierte Vorlagen: einen durchsuchbaren Leseraum für längere Texte und Kapitel, eine Aufgabenliste mit lokalem Abhaken und Hinzufügen, eine Zeitspur für datierte Texte oder einen durchsuchbaren Ideenatlas. Die Wahl entsteht aus sichtbaren lokalen Regeln; sie ist keine allgemeine Sprachmodell-Inferenz. Nicht implementierte Außenfunktionen wie API, Login, Datenbank oder Zahlung bleiben als offene Anschlüsse im JSON erhalten. Der vollständige Eingabetext bleibt erhalten, auch wenn eine Regel ihn nicht deuten kann.

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
