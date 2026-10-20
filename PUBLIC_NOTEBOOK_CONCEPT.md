# Seedspace als öffentliches Notizheft — Entwurf

**Stand:** Konzept, keine Reservierung und keine Zahlungsfunktion. Die bestehende Seedspace-Seite speichert nur den eigenen lokalen Raum.

## Ausgangsidee

Besucher werfen eigene Textkugeln in einen gemeinsamen, begrenzten Raum. Jede Kugel besetzt für eine vereinbarte Zeit einen sichtbaren Platz mit einer begrenzten Größe. Juri hat als mögliche Einstiegssumme **1 BTC** und eine monatliche Erneuerung mindestens in Höhe des anfänglichen Betrags vorgeschlagen. Diese Zahlen sind Produktideen, keine aktive Preisliste oder Zahlungspflicht.

## Platzregel, die man simulieren kann

- Der Raum hat eine veröffentlichte endliche Kapazität `N` und eine fest definierte nutzbare Fläche.
- Ein Beitrag erhält eine eindeutige Slot-ID, einen Eigentümernachweis, einen Mittelpunkt `(x,y)`, einen Radius innerhalb eines veröffentlichten Bereichs sowie `startAt` und `paidThrough`.
- Die Größe kostet Kapazität: Für jeden Slot zählt die belegte Fläche `A = πr²` plus ein sichtbarer Mindestabstand. Neue Kugeln dürfen bestehende Kugeln nicht verdecken. Die Prüfung erfolgt für den gesamten geplanten Zustand vor einer Reservierung.
- Wenn mehrere Personen denselben freien Platz wollen, braucht die Zuteilung eine nachvollziehbare Reihenfolge oder ein vorab definiertes Losverfahren. Ein höherer Betrag verschiebt eine bestehende Kugel nicht heimlich.
- Die Übersicht zeigt freie und belegte Slots sowie deren Größen und Ablaufzeit. Private Zahlungs- und Identitätsdaten gehören nicht in die öffentliche Ansicht.

## Erneuerung und fairer Ausstieg

- Eine Zahlung bezieht sich auf einen klar benannten Nutzungszeitraum. `paidThrough` entscheidet, bis wann der Platz zugesagt ist.
- Eine Verlängerung ist eine neue bewusste Entscheidung. Ohne Verlängerung bleibt der Platz bis zum Ende des bezahlten Zeitraums bestehen; danach kann er nach einer angekündigten Frist frei werden.
- Vor der Freigabe kann der Verfasser seinen Text und die Metadaten exportieren. Eine Freigabe löscht keine historische Git-Version oder öffentliche Kopie automatisch.
- Kein automatischer Strafbetrag, keine Beschlagnahme, kein verdeckter Abzug und keine erzwungene Nachzahlung. Ein getrennt vereinbartes rückzahlbares Sicherheitsguthaben müsste getrennt von der Nutzungsgebühr ausgewiesen und abgerechnet werden.
- „Niemand verliert etwas“ lässt sich bei einer bezahlten Nutzung nicht pauschal versprechen. Fair prüfbar sind zugesagte Laufzeit, Leistung, Rückzahlung ungenutzter Vorauszahlung nach vereinbarter Regel und Datenexport.
- Ein freiwilliger **Ehrenscore** könnte pünktliche Erneuerung und respektvolle Übergabe sichtbar machen. Er ersetzt weder Zahlungsnachweis noch Rechte und darf nicht als öffentliche Bloßstellung für eine Nichtverlängerung dienen.

## Vor einer echten öffentlichen Version zu entscheiden

1. Wer darf veröffentlichen, bearbeiten, löschen und melden? Wie werden Rechte an Text, Bildern und fremden Daten geprüft?
2. Wie funktionieren Konten, Moderation, Missbrauchsmeldungen, Backups, Datenexport und nachvollziehbare Löschfristen?
3. Ist der Betrag eine Nutzungsgebühr, ein rückzahlbares Guthaben oder beides in getrennten Positionen? Welche Währung und welcher Umrechnungskurs gelten für wiederkehrende Beträge?
4. Wie werden Zahlungseingang, Erneuerung, Ablauf, Rückerstattung und Streitfälle technisch und vertraglich belegt?
5. Welche maximale Größe, Mindestabstände, Slotzahl und Laufzeit sind tatsächlich für alle gleich?

**Nächster Prototyp:** zuerst ein lokaler Slot-Simulator mit festen Kapazitätsregeln und Testdaten. Erst nach Prüfung von Preis, Abrechnung, Nutzungsbedingungen und Betreiberaufgaben wäre eine echte Veröffentlichung mit Zahlungsfluss sinnvoll.
