# LUCINET / SEEDSPACE

Lokaler Browser-Prototyp für Juri Janovskis räumliche Kapselidee. Ein Lichtpunkt wird in einen fast bildschirmfüllenden Raum gezogen. Am Ablagepunkt wächst eine Szene aus dem Punkt heraus. Weitere Punkte erzeugen weitere, gleichzeitig bestehende Objekte.

## Start

Im Projektordner `python -m http.server 8851 --bind 127.0.0.1` ausführen und `http://127.0.0.1:8851/` öffnen. Keine Installation, externen Dienste oder Schlüssel erforderlich.

## Bedienung

- Lichtkugel unten greifen und an der gewünschten Stelle loslassen.
- Alternativ Kugel antippen und danach im Raum einen Punkt wählen.
- Mit Tastatur Kugel wählen, Raum fokussieren und Enter oder Leertaste drücken.
- Jeder Kugeltyp hat genau ein Objekt im Raum. Derselbe Typ erneut geworfen: Die bisherige Szene verschwindet sofort und wächst am neuen Ablagepunkt. Andere Typen bleiben stehen.
- Der Raumstand wird nur in diesem Browser gespeichert und nach dem Neuladen mit relativen Positionen wiederhergestellt.
- Objekte über das kleine `×` oder die Liste „Im Raum“ ausblenden und über die Liste wieder einblenden.
- „Raum leeren“ entfernt alle aktuell platzierten Instanzen.
- Das `?` oben rechts enthält Anleitung und Bauplan-Vertrag.

## Modell

`blueprints.js` enthält versionierte, reine Daten für vier registrierte Renderer: Person, Pflanze, Projektatlas und Rechenwerkzeug. `app.js` setzt Position und Richtung der Entfaltung am tatsächlichen Ablagepunkt. Die Wurfanimation führt zum Punkt, die Szene wächst dort. Pro Bauplan bleibt höchstens eine Instanz; ein neuer Wurf ersetzt den alten Ort samt altem Lichteffekt. `room-state.js` speichert nur Bauplan-IDs, relative Positionen und Sichtbarkeit im lokalen Browser. Alte lokale Räume mit doppelten Bauplänen werden beim Laden auf den jeweils letzten Ort reduziert. Das Microvalue-Werkzeug rechnet direkt im Browser.

Die Kapsel führt keinen fremden Code aus und liest keine Excel-Datei. Eine spätere Projektkapsel könnte ein geprüftes, freigegebenes Datenpaket in einen isolierten Renderer laden. Die Browserfassung ist noch keine dreidimensionale Spielwelt und keine Morrowind-Integration; ihr Zustandsmodell ist als Ausgangspunkt dafür gedacht.
