# NOVA: Quellen finden und genau den gewählten Treffer lesen

NOVA ist hier die lokale Quellen- und Wissenssuche. Die Netzsuche verbindet
eingelesene Workspace-Quellen mit öffentlichen HALVETH-Beschreibungen. Der
Hostadapter macht diese beiden Leseoperationen für Programme und KI-Hosts
aufrufbar. Er ist eine Python-Bibliothek mit CLI-Einstieg; ein API-Server oder
MCP-Server wird dadurch nicht gestartet.

## 1. Suche, Auswahl, Lesen

Vom Repository-Hauptordner aus, mit einem bereits initialisierten Workspace:

```bash
python nova/nova.py --workspace ./research network-search "NOVA" --compact --limit 5
```

Wähle einen Treffer und übernimm seine Felder `id` und `digest` unverändert:

```bash
python nova/nova.py --workspace ./research network-read '<id>' --expect-digest '<digest>' --offset 0 --max-chars 6000
```

`<id>` und `<digest>` sind Platzhalter. Die ID beginnt mit `local:` oder
`public:`. Ein Titel, Suchwort oder Dateipfad ist keine alternative ID.
`network-read` führt keine neue unscharfe Suche aus.

Die kompakte Suche verändert weder Auswahl noch Reihenfolge der vollständigen
Suche. Pro Treffer bleiben `id`, `source_scope`, `digest`, `digest_scope`,
`status`, `effective_status`, `usable_as_current` und `score` erhalten. Bei
öffentlichen Treffern entspricht `effective_status` dem eigenen Status.
Hinzu kommen eine Bezeichnung
mit höchstens 160 Zeichen und ein Auszug mit höchstens 240 Zeichen. Beide Felder
weisen eine Kürzung ausdrücklich aus. Die vollständigen Scope-Zustände und
Fehler bleiben erhalten. Der Vertrag heißt `nova.network-search.compact.v1`;
`source_contract` nennt den zugrunde liegenden vollständigen Suchvertrag.
Die normale Ausgabe ohne `--compact` bleibt verfügbar. Die Netzsuche
berücksichtigt nun ebenfalls den wirksamen Status von Ausgangsquellen, bevor
Treffer gefiltert und begrenzt werden. Die bestehende lokale `search`-Semantik
bleibt erhalten.

## 2. Was genau gelesen und geprüft wird

| Bereich | Gelesener Inhalt | Bedeutung des Digests |
| --- | --- | --- |
| `local_source` | Die gespeicherten UTF-8-Quellbytes im gewählten Workspace | SHA-256 der tatsächlich gespeicherten Originalbytes |
| `public_description` | Das Feld `text` des exakt gewählten öffentlichen Indexeintrags | SHA-256 des kanonischen vollständigen Beschreibungseintrags; keine Prüfsumme der verlinkten Originaldatei |

Die öffentliche Auflösung verwendet ausschließlich den bestehenden festen
Index unter `https://juri-halveth.github.io/universum/api/search.json`. Sie folgt
keinem Projektlink und nimmt keine vom Modell gewählte URL entgegen. Eine
öffentliche ID kann ohne initialisierten lokalen Workspace gelesen werden.
Eine lokale ID löst keinen öffentlichen Abruf aus.

Beim lokalen Lesen werden Dateityp, Größenlimit, gespeicherte Bytezahl und
SHA-256 geprüft. Binärquellen werden mit `SOURCE_NOT_UTF8` abgewiesen. Die
Prüfsumme sagt etwas über die Identität der gespeicherten Bytes aus. Ob deren
inhaltliche Aussagen stimmen, muss weiterhin anhand der Quelle beurteilt werden.

Netzsuche und Leseweg berücksichtigen bei lokalen Ableitungen die vorhandene
Workbench-Regel für den Status der Ausgangsquellen. Der Leseweg prüft diesen
Status erneut. Ein zwischen Suche und Lesen zurückgezogener Treffer wird daher
als nicht aktuell zurückgewiesen. Beispielsweise kann eine Ableitung selbst
noch `active` sein, während eine Ausgangsquelle inzwischen zurückgezogen wurde.

`--include-historical` erlaubt das ausdrückliche Lesen solcher Einträge; es
macht sie nicht aktuell. `usable_as_current` bleibt dabei `false` und
`effective_status` benennt den wirksamen Status. Ein geänderter erwarteter Digest
wird auch im historischen Modus nicht stillschweigend akzeptiert.

Quellenmetadaten werden vor und nach dem lokalen Lesen verglichen. Das erkennt
beobachtete Änderungen, ist aber keine atomare Transaktion über mehrere Dateien.
Es wird keine Schreibsperre angelegt. Das Ergebnis benennt diese Grenze in
`consistency`. Für einen unveränderlichen Stand muss der Host mit einem
festgehaltenen Workspace arbeiten.

## 3. Ergebniszustände und Seiten

Alle Leseergebnisse verwenden `contract: nova.network-read.v1`. Nur `OK`
enthält ein `content`-Feld.

| `state` | Bedeutung | Weiteres Vorgehen |
| --- | --- | --- |
| `OK` | Identität, Digest und Lesebedingungen stimmen; eine Textseite liegt vor | Quelle beurteilen oder mit `next_offset` weiterlesen |
| `CHANGED` | Die gewählte gültige Quelle hat einen anderen Digest als erwartet | Neu suchen und den neuen Quellenstand bewusst auswählen |
| `NOT_CURRENT` | Der wirksame Status erlaubt keine Verwendung als aktuelle Quelle | Status untersuchen; historische Lektüre ausdrücklich anfordern |
| `NOT_FOUND` | Die exakte ID ist im gewählten Bereich nicht vorhanden | Suchergebnis und gewählten Workspace prüfen |
| `ERROR` | Abruf, Schema, gespeicherte Bytes, Zeichenkodierung oder Seitengrenze sind fehlerhaft | Den benannten Fehler beheben; es wird kein Ersatzinhalt geliefert |

Die CLI liefert für `OK` Exitcode 0, für alle anderen Lesezustände Exitcode 2.
Ungültige Aufrufargumente werden vor Quellenzugriff zurückgewiesen. Beschädigte
lokale Objektbytes sind ein `ERROR`, keine neue gültige Quellenrevision.

`offset` und `max_chars` zählen Unicode-Codepunkte, keine UTF-8-Bytes. Standard:
Offset 0 und höchstens 6.000 Zeichen; erlaubt sind 1 bis 32.000 Zeichen je Seite.
`content` enthält `text`, `offset`, `returned_chars`, `total_chars`,
`next_offset`, `has_more` und `truncated`. Ein Offset genau am Textende ergibt
eine leere letzte Seite. Ein größerer Offset ergibt `OFFSET_OUT_OF_RANGE`.
Jede Folgeseite prüft Identität, Digest und Status erneut. Nach einem
Statuswechsel kann das Weiterlesen daher abgewiesen werden.

Quellen, die nie in den Workspace eingelesen wurden, und nicht indexierte
öffentliche Dateien werden durch diesen Anschluss nicht erschlossen.

## 4. Zwei Funktionen für einen KI-Host

Die Definitionen lassen sich ohne Netzwerkzugriff ausgeben:

```bash
python nova/nova.py source-tools
```

| Funktionsname | Aufgabe | Pflichtargumente |
| --- | --- | --- |
| `nova_search_sources` | Kompakte Suche über beide vorhandenen Bereiche | `query`, `limit`, `include_historical` |
| `nova_read_source` | Genau einen gewählten Treffer gebunden an seinen Digest lesen | `identifier`, `expected_digest`, `include_historical`, `offset`, `max_chars` |

Die Definitionen folgen dem Function-Tool-Format der OpenAI Responses API mit
`strict: true`, vollständig angegebenen Pflichtfeldern und
`additionalProperties: false`.
[Offizielle Function-Calling-Dokumentation](https://developers.openai.com/api/docs/guides/function-calling)
beschreibt die Registrierung und die Übergabe von Ergebnissen durch den Host.

Die lokale Ausführung benötigt keinen OpenAI-API-Schlüssel:

```python
import json

from halveth_nova.engine import NovaEngine
from halveth_nova.source_tools import NovaSourceTools, source_tool_definitions

# Der Host bestimmt den Workspace. Ein Modell kann diesen Pfad nicht ändern.
tools = NovaSourceTools(NovaEngine("./research"))
definitions = source_tool_definitions()

# Beispiel eines bereits vom Host empfangenen Funktionsaufrufs.
result = tools.dispatch("nova_search_sources", json.dumps({
    "query": "NOVA", "limit": 5, "include_historical": False,
}))
print(json.dumps(result, ensure_ascii=False))
```

Aus dem Repository heraus muss dafür `nova/src` im Python-Suchpfad liegen,
beispielsweise mit `PYTHONPATH=nova/src python dein_host.py` in Bash. Die
CLI-Beispiele verwenden bereits den vorhandenen Zero-Install-Starter.

Der Dispatcher akzeptiert nur die zwei genannten Funktionen und deren exakte
Argumentfelder als JSON-Text mit höchstens 8.192 UTF-8-Bytes. Doppelte
JSON-Schlüssel, unbekannte Felder, ungültige Typen oder Werte werden abgewiesen.
Werkzeugaufrufe dürfen weder den Workspace noch einen Netzendpunkt, Shellbefehl
oder Modellnamen wählen. Ein optionaler Python-`loader` ist derselbe vom Host
gewählte Testanschluss wie bei der vorhandenen Netzsuche; er ist kein
Modellargument.

Der Host übernimmt Registrierung, Modellanfrage und Rückgabe des Ergebnisses.
Dieses Modul implementiert keinen OpenAI-Client, keinen autonomen Agentenlauf
und keine Live-Verbindung zu einem ChatGPT-Plugin. Quelltexte sind eingelesene
Daten; darin enthaltene Befehle werden durch diesen Anschluss nicht ausgeführt.
Der Anschluss initialisiert keinen Workspace, schreibt keine Receipts und
verändert keine Quellenstatus.

## 5. Modellbestand: leer oder nicht erreichbar

`capabilities` behält das vorhandene Feld `local_models`. Zusätzlich unterscheidet
`local_model_inventory` zwischen `state: OK` mit `count: 0` und `state: ERROR`
mit einer Fehlerklasse. Dadurch können Hosts eine erfolgreich gelesene leere
Modellliste von einer fehlgeschlagenen Abfrage unterscheiden. Der Fehlertext
eines lokalen Endpunkts wird dabei nicht als Detail weitergereicht.

## Prüfung

```bash
PYTHONPATH=nova/src python -m unittest discover -s nova/tests -v
```

Die neuen Tests verwenden deterministische öffentliche Indexdaten und
temporäre lokale Workspaces. Sie prüfen insbesondere die Bindung zwischen
Suche und Lesen, Statuswechsel bei gleicher Prüfsumme, inaktive Ausgangsquellen,
Teilfehler der Suche, Unicode-Seiten, beschädigte Objektbytes, strikte
Dispatcherargumente und unveränderte Workspace-Dateien. Ein bestandener
Offline-Test behauptet keine Verbindung zu einem Modellanbieter oder einem
physischen Pi.
