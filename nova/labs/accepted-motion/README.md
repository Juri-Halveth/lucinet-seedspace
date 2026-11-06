# NOVA · akzeptierte Bewegungsfassung

Die frei steuerbare fiktive erwachsene Figur wurde am **06.11.2026 vom
Projektinhaber visuell als glaubwürdig und deutlich besser als frühere
Versuche akzeptiert**. Dieser Stand wird erhalten. Seine Bewegung wird hier
nicht erneut umgebaut.

## Lokal öffnen

Python 3.11+ genügt zum Anzeigen; Browsergrafik und Assets liegen im Paket.

```sh
python nova/labs/accepted-motion/serve.py
```

Danach **http://127.0.0.1:31350/motion/** öffnen. Unter Windows startet
`START.cmd` denselben lokalen Server. WASD/Pfeiltasten bewegen die Figur;
Ziehen dreht die Kamera. Der Prüfknopf zeigt Stehen, Gehen, Wenden und Stoppen.
Zum Beenden im Serverfenster Strg+C drücken.
Der Server bindet ausschließlich an 127.0.0.1 und setzt JavaScript-MIME-Typen
explizit, damit Windows-Dateizuordnungen den Modulstart nicht verhindern.

Der ursprüngliche private VERACHEL/NOVA-Arbeitsraum bleibt separat bestehen.
Dieses eigenständig ausführbare Labor enthält die akzeptierte Bewegungsfassung,
keine privaten Journale, Chats, Quellenbestände oder Modellzugänge.

## Was genau erhalten ist

[`FROZEN_FILES.json`](FROZEN_FILES.json) bindet die **21 ursprünglichen Dateien**
einschließlich Renderer, Controller, Retargeting, Bibliotheken und Grafikdaten
bytegenau. Nur ihr gemeinsamer übergeordneter Ordner wurde für den lokalen
`/motion/`-Pfad angepasst. Die Renderer- und Bewegungsbytes sind unverändert.

```sh
python nova/labs/accepted-motion/verify.py
node --test nova/labs/accepted-motion/motion/motion-boundary.test.mjs
python nova/labs/accepted-motion/measure.py motion-results-new
```

Die letzte Zeile benötigt Node.js 22+ und einen noch nicht vorhandenen
Ausgabeordner. Sie erzeugt beide Messspuren mit je 660 Modellschritten in
einer temporären Kopie. Dafür wird der vom historischen Messskript erwartete
Ausgabeordner angelegt; die eingefrorenen Quelldateien bleiben unverändert.

## Visuelle Abnahme und technische Messung

| Achse | Stand |
| --- | --- |
| Visuelle Nutzerabnahme | `USER_ACCEPTED_VISUAL_BASELINE`, 06.11.2026 |
| Bewegung | Kinematischer Controller, animiertes Skelett mit 65 Gelenken |
| Messung | Beide Sohlen bleiben über Animationswechsel hinweg adressierbar |
| Freier Stopp | 47,127 mm maximaler gemessener Versatz pro 1/60-s-Schritt |
| Sechs zusätzliche Stoppzeitpunkte | Bis 61,498 mm am ausgewählten Standfuß |
| Kräfte, Gleichgewicht, Selbst-/Kleidungskollision | Nicht abgenommen |

Die visuelle Abnahme ist eine eigene Nutzerentscheidung. Sie verändert weder
die aufgezeichneten Messwerte noch die Reichweite der bisherigen Versuche.
Eine stilisierte weibliche Figur belegt keine abgeschlossene Entwicklung
hochwertiger männlicher und weiblicher Menschenmodelle.

Die getrennte private Integrationsprüfung umfasste einen gebundenen
Quellenabruf und einen Übergang zwischen zwei frisch gestarteten
Modellprozessen. Das ist kein Bestandteil dieses öffentlichen Grafiklabors.
[`ACCEPTANCE.json`](ACCEPTANCE.json) verknüpft den erhaltenen lokalen
Prüfpaket-Digest mit dieser Entscheidung, ohne dessen Inhalte zu verteilen.

## Arbeitspause und Wiederaufnahme

Nach Sicherung und GitHub-Abschluss ruht die Weiterentwicklung dieses
Arbeitsstrangs bis **13.11.2026**. Es ist kein automatischer Neustart,
Modellaufruf, Scan oder Umbau eingeplant. Ein neuer Nutzerauftrag kann die
Pause ändern. Eine spätere Bewegungsänderung beginnt als neue Kandidatenfassung;
diese akzeptierten Bytes bleiben über Git und das Manifest erreichbar.

## Herkunft und Rechte

Die [Datei-Lizenzkarte](LICENSES.md) trennt HALVETH-Code, den GPL-Builder,
Three.js unter MIT und die CC0-Grafik-/Animationsdaten von Quaternius.
Historische und fremde Rechte werden durch diese Sicherung nicht geändert.
