# NOVA · frühere Arbeit wiederfinden und nachvollziehbar fortsetzen

NOVA ist ein lokales Python-Werkzeug für Menschen, die mit vielen Notizen,
Quelltexten und Forschungsständen arbeiten: Es findet Quellen wieder, erhält
Korrekturen und schreibt auf, worauf ein Ergebnis beruht und was als Nächstes ansteht.

**Python 3.11+ · Windows / Linux / macOS · Quellen und Basisanalyse lokal ·
keine zusätzlichen Python-Laufzeitpakete für den Kern**

## In einer Minute anfangen

```sh
git clone https://github.com/Juri-Halveth/lucinet-seedspace.git
cd lucinet-seedspace
python nova/nova.py --workspace ./nova-demo demo
python nova/nova.py --workspace ./nova-demo verify
```

Der erste Befehl baut in einem **neuen** Arbeitsverzeichnis eine Beispielsammlung,
führt Analysen und Gegenproben aus und nennt die erzeugte lokale HTML-Ansicht.
Der zweite prüft die gespeicherten Quellen, Ergebnisse und Fortsetzungsdaten.
Für einen weiteren unabhängigen Probelauf einen neuen Workspace-Namen wählen.

## Drei Aufgaben, ein nachvollziehbarer Weg

| Aufgabe | Was NOVA macht | Ergebnis zum Prüfen |
| --- | --- | --- |
| „Hatten wir das schon untersucht?“ | Lokale Quellen indexieren und passende Stellen mit ihrem Status finden | Datei, Fundstelle, Revision und erhaltene Originalbytes |
| „Die alte Erklärung wurde korrigiert.“ | Frühere und aktuelle Lesarten getrennt erhalten | Suchbare Historie statt versehentlich wiederbelebter Behauptung |
| „Wo machen wir morgen weiter?“ | Ergebnis, offene Fragen und nächsten Schritt in einem Receipt speichern | Überprüfbarer Resume-Stand und portabler Export |

```text
Notizen / Code → Quellenbestand → Suche & Gegenprobe → Ergebnis + nächster Schritt
                      ↑                                   │
                      └──────── später wiederfinden ──────┘
```

[Vollständige CLI-Anleitung](nova/README.md) ·
[Workbench und Integrationen](nova/WORKBENCH.md) ·
[Molekül-Labor](nova/labs/molecular-lineage/README.md) ·
[Sicherheitsmodell](nova/SECURITY_MODEL.md)

## Selbst prüfen

```sh
python -m compileall -q nova/src nova/nova.py
```

Linux / macOS: `PYTHONPATH=nova/src python -m unittest discover -s nova/tests -v`

PowerShell:

```powershell
$env:PYTHONPATH = "nova/src"
python -m unittest discover -s nova/tests -v
```

[CI-Läufe](https://github.com/Juri-Halveth/lucinet-seedspace/actions/workflows/nova-core.yml)
führen die NOVA-Tests auf Windows und Linux aus. Die Prüfumfänge stehen in den
einzelnen Läufen. Ein Integritätscheck prüft den gespeicherten Zustand;
externe Quellenwahrheit und Nutzen im Alltag benötigen ihre eigene Prüfung.

## Weiteres in diesem Repository

Der ursprüngliche **Seedspace-Kugelraum** bleibt als getrennte Browserarbeit
erreichbar: [Browserraum öffnen](https://juri-halveth.github.io/lucinet-seedspace/) ·
[erhaltene Anleitung](SEEDSPACE.md).
Die NOVA-CLI und der Kugelraum haben unterschiedliche Einstiege und Aufgaben.

## Verwandte öffentliche Forschung

Die [HALVETH-Wissensübersicht](https://juri-halveth.github.io/halveth-forschungslabor/wissen/)
gehört zum getrennten [Forschungslabor-Repository](https://github.com/Juri-Halveth/halveth-forschungslabor).
Dort werden dessen öffentliche Module mit Quellen, Tests und bekannten Grenzen
verbunden. NOVA kann daraus eine begrenzte Auswahl öffentlicher Dateien lokal
lesen; eine Prüfung privater Arbeitsstände oder aller HALVETH-Projekte folgt
daraus nicht.

## Lizenz und Kontakt

NOVA ist **source-available unter HALVETH PIRL 2.0** mit den ausdrücklich
aufgeführten MIT-Ausnahmen: [Lizenzkarte](nova/LICENSES.md).
Die Herkunfts- und Lizenzstände des übrigen Repositorys bleiben erhalten.

Zusammenarbeit: **[juri@halveth.de](mailto:juri@halveth.de)** ·
Sicherheitsmeldungen: **[security@halveth.de](mailto:security@halveth.de)**

Projektleitung und Auswahl: Juri / HALVETH · Entwicklung mit KI-Unterstützung.
