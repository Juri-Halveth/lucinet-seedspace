# LUCINET / SEEDSPACE

Lokaler Browser-Prototyp für Juri Janovskis Idee vom leuchtenden Punkt, der beim Platzieren einen vorbereiteten Bauplan sichtbar entfaltet. Vier Kapseln zeigen unterschiedliche Resultate: Vorstellung, Pflanze, Projektatlas und ein interaktives Rechenwerkzeug.

## Start

Im Projektordner `python -m http.server 8851` ausführen und `http://127.0.0.1:8851/` öffnen. Keine Installation und keine externen Dienste erforderlich.

## Technischer Vertrag

`blueprints.js` enthält nur Daten mit Version, ID und Renderer-Typ. `app.js` erlaubt ausschließlich registrierte lokale Renderer. Eine Kapsel wählt beim Aufprall die Position und den Renderer; eine Flug- und Entfaltungsanimation macht den Übergang sichtbar. Das Werkzeug rechnet im Browser. Es gibt keinen Import fremden Codes, keinen Zugriff auf Excel-Dateien und keine automatische Ausführung externer Aktionen.

Die Szene ist eine Websimulation. Ein ähnliches Ereignismodell könnte später in einer Spielwelt oder einem anderen Frontend benutzt werden, aber diese Browserfassung ist keine Morrowind-Integration.

## Bedienung

- Kapsel anklicken und danach im Raum klicken; alternativ hineinziehen.
- Mit Tastatur Kapsel wählen und im fokussierten Raum Enter oder Leertaste drücken.
- `Entfaltung wiederholen` spielt die letzte Kapsel erneut; `Raum leeren` setzt zurück.
- Bei reduzierter Bewegung werden Flug und Entfaltung stark verkürzt.

## Nächste Erweiterung

Eine echte Projektkapsel könnte eine freigegebene, versionierte lokale Datenquelle laden und in einem isolierten Renderer anzeigen. Dafür braucht es einen eigenen Importvertrag für Dateiformat, Größe, Rechte, Validierung und eine Vorschau vor dem Öffnen.
