# LUCINET / SEEDSPACE

Lokaler Browser-Prototyp für Juri Janovskis räumliche Kapselidee. Ein Lichtpunkt wird in einen fast bildschirmfüllenden Raum gezogen. Am Ablagepunkt wächst eine Szene aus dem Punkt heraus. Weitere Punkte erzeugen weitere, gleichzeitig bestehende Objekte.

## Start

Im Projektordner `python -m http.server 8851 --bind 127.0.0.1` ausführen und `http://127.0.0.1:8851/` öffnen. Keine Installation, externen Dienste oder Schlüssel erforderlich.

## Bedienung

- Lichtkugel unten greifen und an der gewünschten Stelle loslassen.
- Alternativ Kugel antippen und danach im Raum einen Punkt wählen.
- Mit Tastatur Kugel wählen, Raum fokussieren und Enter oder Leertaste drücken.
- Jede Kapsel erzeugt eine eigene Instanz. Bereits platzierte Objekte bleiben erhalten.
- Objekte über das kleine `×` oder die Liste „Im Raum“ ausblenden und über die Liste wieder einblenden.
- „Raum leeren“ entfernt alle aktuell platzierten Instanzen.
- Das `?` oben rechts enthält Anleitung und Bauplan-Vertrag.

## Modell

`blueprints.js` enthält versionierte, reine Daten für vier registrierte Renderer: Person, Pflanze, Projektatlas und Rechenwerkzeug. `app.js` setzt Position und Richtung der Entfaltung am tatsächlichen Ablagepunkt. Die Wurfanimation führt zum Punkt, die Szene wächst dort, und ihre Instanz bleibt im Raum. Mehrere Instanzen desselben Bauplans sind möglich. Das Microvalue-Werkzeug rechnet direkt im Browser.

Die Kapsel führt keinen fremden Code aus und liest keine Excel-Datei. Eine spätere Projektkapsel könnte ein geprüftes, freigegebenes Datenpaket in einen isolierten Renderer laden. Die Browserfassung ist noch keine dreidimensionale Spielwelt und keine Morrowind-Integration; ihr Zustandsmodell ist als Ausgangspunkt dafür gedacht.
