// SPDX-License-Identifier: MIT
// Source-bound answers shared by the detail view and W-coverage matrix.
const findingText = {possible_object:'möglicher Gegenstand', alternative_explanation:'andere Erklärung', unresolved:'offen'};

const w = (question, value, state='UNKNOWN') => ({question, value, state});
export function syntheticWRows(item, result) {
  const packet = item.packet;
  const origins = [...new Set(result.rows.map(row => row.declaredOriginId))];
  const findings = [...new Set(result.rows.map(row => findingText[row.finding]))];
  const originals = result.rows.filter(row => row.kind === 'ORIGINAL_DECLARED');
  const ages = originals.map(row => row.ageMinutes).filter(Number.isFinite);
  const copies = result.reportCount - result.originalReportCount;
  const ageText = ages.length
    ? `${Math.min(...ages).toFixed(0)}–${Math.max(...ages).toFixed(0)} Minuten zum Referenzzeitpunkt`
    : 'UNKNOWN – keine vollständige Beobachtungszeit';
  return [
    w('WER?', origins.length ? origins.join(', ') + ' · nur deklarierte Ursprünge' : 'UNKNOWN', 'DEKLARIERT'),
    w('WEN?', 'UNKNOWN – betroffene Person/Entität ist kein Feld dieses Modells'),
    w('WEM?', 'UNKNOWN – konkrete Empfängerrolle ist nicht gebunden'),
    w('WESSEN?', 'UNKNOWN – Eigentum, Zuständigkeit und Rechte werden nicht aus originId geraten'),
    w('WAS?', findings.join(' · ') || 'UNKNOWN', findings.length ? 'DEKLARIERT' : 'UNKNOWN'),
    w('WANN?', `Referenz: ${packet.referenceTime} · Frischefenster: ${packet.freshnessMinutes} min`, 'BELEGT'),
    w('WIE LANGE?', ageText, ages.length ? 'ABGELEITET' : 'UNKNOWN'),
    w('WIE OFT?', `${result.reportCount} Meldungen · ${copies} Weitergaben · Revisionszahl außerhalb der Kette UNKNOWN`, 'ABGELEITET'),
    w('WO?', 'UNKNOWN – kein Ortsfeld im synthetischen Vertrag'),
    w('WOHER?', origins.length ? origins.join(', ') + ' · nicht authentisiert' : 'UNKNOWN', 'DEKLARIERT'),
    w('WOHIN?', 'Menschliche Prüfung; das Modell trifft keine Lageentscheidung', 'BELEGT'),
    w('WIE?', 'Original-/Kopierkette über parentId; Beobachtung und Empfang bleiben getrennt', 'BELEGT'),
    w('WARUM?', 'UNKNOWN – Ursache oder Motiv des Ereignisses ist nicht enthalten'),
    w('WESHALB?', `Aktueller Prüfstatus: ${result.status}; abgeleitet aus Kopien, Zeitfenster und Befunden`, 'ABGELEITET'),
    w('WOFÜR?', 'Doppelzählungen, alte Beobachtungen und Widersprüche vor einer menschlichen Entscheidung sichtbar machen', 'BELEGT'),
    w('WOMIT?', 'caseId, originId, parentId, observedAt, receivedAt und finding', 'BELEGT'),
    w('WODURCH?', 'Zusammenhang nur durch deklarierte Kopierkante und unveränderte Beobachtung; Herkunft nicht authentisiert', 'BELEGT'),
    w('WELCHE VERSION?', `${result.contract} · Fall ${result.caseId}`, 'BELEGT'),
    w('WIE SICHER?', `Außenlage: ${result.worldState} · Herkunftsauthentisierung: ${result.sourceAuthentication}`, 'BELEGT'),
    w('WAS WENN?', 'Bei Widerspruch, Zeitlücke, offenem Befund oder nur einer Quelle bleibt die Prüfung offen', 'BELEGT'),
    w('WIE WEITER?', result.action === 'HUMAN_REVIEW_ONLY' ? 'HUMAN_REVIEW_ONLY' : result.action, 'BELEGT'),
    w('WAS FEHLT?', 'Authentisierte Quelle, Ort, Betroffene, Ursache/Motiv, Sensorweg, Rechte/Zuständigkeit und unabhängige Außenbeobachtung')
  ];
}

export function realWRows(snapshot, result) {
  const summary = snapshot.records.summary;
  const p = summary.properties ?? {};
  const coords = Array.isArray(summary.geometry?.coordinates) ? summary.geometry.coordinates : [];
  const where = [p.place || (p.title ? 'Ortsbezug nur im Titel: '+p.title : null), coords.length >= 2 ? `lon ${coords[0]}, lat ${coords[1]}` : null].filter(Boolean).join(' · ');
  const eventAt = Date.parse(result.eventTimeSummary);
  const retrievedAt = Date.parse(snapshot.feed.retrievedAt);
  const delayMinutes = Number.isFinite(eventAt) && Number.isFinite(retrievedAt)
    ? ((retrievedAt-eventAt)/60000).toFixed(0) + ' Minuten Ereignis → Feed-Abruf'
    : 'UNKNOWN';
  return [
    w('WER?', 'USGS als Katalog-Publisher; physische Sensoren/Operatoren in dieser Probe UNKNOWN', 'BELEGT'),
    w('WEN?', 'UNKNOWN – betroffene Menschen/Organisationen werden aus diesem Katalogeintrag nicht abgeleitet'),
    w('WEM?', 'Öffentlicher Datenzugang; LAGEFADEN zeigt ihn einer menschlichen Prüferin/einem menschlichen Prüfer', 'BELEGT'),
    w('WESSEN?', 'Katalogdarstellung: USGS; weitergehende Eigentums-/Zuständigkeitsfragen werden nicht geraten', 'BELEGT'),
    w('WAS?', result.title, 'BELEGT'),
    w('WANN?', `Ereignis ${result.eventTimeSummary} · Update ${result.updateTimeDetail} · Abruf ${snapshot.feed.retrievedAt}`, 'BELEGT'),
    w('WIE LANGE?', delayMinutes, delayMinutes === 'UNKNOWN' ? 'UNKNOWN' : 'ABGELEITET'),
    w('WIE OFT?', `${result.representationCount} API-Darstellungen · 1 gemeinsame Ereigniskennung · Anzahl physischer Beobachtungen UNKNOWN`, 'BELEGT'),
    w('WO?', where || 'UNKNOWN – kein auswertbarer Ort/Koordinatenwert', where ? 'BELEGT' : 'UNKNOWN'),
    w('WOHER?', `Feed: ${snapshot.feed.url} · Detail: ${snapshot.detail.url}`, 'BELEGT'),
    w('WOHIN?', 'Gebundener lokaler Snapshot → LAGEFADEN → menschliche Prüfung', 'BELEGT'),
    w('WIE?', 'Zwei GeoJSON-Repräsentationen werden über dieselbe USGS-Ereigniskennung verglichen; Sensorweg wird nicht erfunden', 'BELEGT'),
    w('WARUM?', 'UNKNOWN – geologische Ursache wird aus diesem Datenweg nicht hergeleitet'),
    w('WESHALB?', result.eventTimeMatches ? 'Gleiche Event-ID und gleiche Ereigniszeit tragen die Einstufung „ein Katalogereignis“' : 'Gleiche Event-ID, aber Zeitabweichung → offene Prüfung', 'ABGELEITET'),
    w('WOFÜR?', 'Quellen-, Zeit- und Kopienprüfung vor einer menschlichen Entscheidung', 'BELEGT'),
    w('WOMIT?', 'Offizieller USGS-GeoJSON-Feed, Detail-URL, Abrufzeiten, Bytezahlen und SHA-256-Receipts', 'BELEGT'),
    w('WODURCH?', 'Gemeinsame Event-ID bindet die Darstellungen katalogseitig; unabhängige Sensorherkunft bleibt UNKNOWN', 'BELEGT'),
    w('WELCHE VERSION?', `${snapshot.contract} · Katalog-Update ${result.updateTimeDetail} · Snapshot ${snapshot.feed.retrievedAt}`, 'BELEGT'),
    w('WIE SICHER?', 'Gleiches USGS-Katalogereignis: belegt durch ID/Zeiten. Sensorunabhängigkeit und Außenlage: UNKNOWN', 'BELEGT'),
    w('WAS WENN?', 'Weichen Event-ID oder Ereigniszeit ab, wird nicht automatisch zusammengeführt; menschliche Prüfung', 'BELEGT'),
    w('WIE WEITER?', 'Rohantwort-Fixtures für Replay bewahren und eine belegte Ereigniszuordnung zwischen Katalogen gegen Gegenfälle testen', 'BELEGT'),
    w('WAS FEHLT?', 'Authentisierte Sensorprovenienz, Zahl unabhängiger Messungen, vollständige Revisionsgeschichte, Betroffene, Ursache und konkreter Nutzerworkflow')
  ];
}

export const wQuestions = ['WER?','WEN?','WEM?','WESSEN?','WAS?','WANN?','WIE LANGE?','WIE OFT?','WO?','WOHER?','WOHIN?','WIE?','WARUM?','WESHALB?','WOFÜR?','WOMIT?','WODURCH?','WELCHE VERSION?','WIE SICHER?','WAS WENN?','WIE WEITER?','WAS FEHLT?'];
export const unavailableWRows = () => wQuestions.map(question => w(question,'UNKNOWN – gültiger Snapshot fehlt'));

export function eonetWRows(snapshot, result) {
  const geometry = snapshot.records.detail.geometry;
  const spanHours = (Date.parse(result.lastGeometryTime)-Date.parse(result.firstGeometryTime))/3600000;
  const {latitude,longitude} = result.lastLocation;
  const place = Math.abs(latitude) + '° ' + (latitude < 0 ? 'S' : 'N') + ', ' + Math.abs(longitude) + '° ' + (longitude < 0 ? 'W' : 'E');
  return [
    w('WER?', 'NASA EONET als Katalog; ' + result.sourceReferenceIds.join(', ') + ' als verlinkte Quellen, nicht als bestätigte Sensoren', 'BELEGT'),
    w('WEN?', 'UNKNOWN – betroffene Personen/Organisationen sind kein Feld dieses Snapshots'),
    w('WEM?', 'Öffentlicher Katalogzugang; LAGEFADEN zeigt den Eintrag einer prüfenden Person', 'BELEGT'),
    w('WESSEN?', 'Katalogdaten von EONET; Rechte und Zuständigkeiten der verlinkten Quellen: UNKNOWN'),
    w('WAS?', result.title + ' · kuratierter Ereignistitel', 'BELEGT'),
    w('WANN?', 'Erste/letzte Geometriezeit: ' + result.firstGeometryTime + ' / ' + result.lastGeometryTime + ' · Abruf ' + snapshot.list.retrievedAt, 'BELEGT'),
    w('WIE LANGE?', spanHours + ' Stunden zwischen erstem und letztem Katalogpunkt; Ereignisdauer UNKNOWN', 'ABGELEITET'),
    w('WIE OFT?', result.representationCount + ' API-Ansichten · ' + geometry.length + ' Geometriepunkte · 1 EONET-ID; unabhängige Messungen UNKNOWN', 'BELEGT'),
    w('WO?', 'Letzter Katalogpunkt: ' + place + '; Ortsgenauigkeit UNKNOWN', 'BELEGT'),
    w('WOHER?', snapshot.list.url + ' · ' + snapshot.detail.url, 'BELEGT'),
    w('WOHIN?', 'Minimierter lokaler Snapshot → LAGEFADEN → menschliche Prüfung', 'BELEGT'),
    w('WIE?', 'EONET-Liste und kanonisches Detail über dieselbe Event-ID verglichen', 'BELEGT'),
    w('WARUM?', 'UNKNOWN – Entstehungsursache und physischer Mechanismus sind nicht Teil des Datenvertrags'),
    w('WESHALB?', result.referencesMatch ? 'Gleiche Event-ID und gleiche Quellverweis-IDs in beiden Ansichten' : 'Quellverweise weichen ab → Prüfung offen', 'ABGELEITET'),
    w('WOFÜR?', 'Katalogansichten und Zeitstand vor einer menschlichen Einordnung auseinanderhalten', 'BELEGT'),
    w('WOMIT?', 'EONET-JSON, zwei Abrufreceipts mit Zeiten, Bytezahlen und SHA-256', 'BELEGT'),
    w('WODURCH?', 'Gleiche EONET-ID bindet die Ansichten; Links allein binden keine Sensoridentität', 'BELEGT'),
    w('WELCHE VERSION?', snapshot.contract + ' · Detailabruf ' + snapshot.detail.retrievedAt, 'BELEGT'),
    w('WIE SICHER?', 'Katalogidentität quellengebunden; Sensorunabhängigkeit und Außenlage UNKNOWN', 'BELEGT'),
    w('WAS WENN?', 'Ändern sich Quellverweise oder Geometriezeiten, muss ein neuer Abruf getrennt geprüft werden', 'BELEGT'),
    w('WIE WEITER?', 'Verlinkte Originalquellen und Revisionen separat prüfen; keine katalogübergreifende Identität raten', 'BELEGT'),
    w('WAS FEHLT?', 'Authentisierte Messkette, unabhängige Beobachtungszahl, Betroffene, Ereignisdauer, Kausalursache und Revisionsgeschichte')
  ];
}

export function cemsWRows(snapshot, result) {
  const lagHours = (Date.parse(result.activationTime)-Date.parse(result.eventTime))/3600000;
  const countries = Array.isArray(snapshot.records.mapping.countries) ? snapshot.records.mapping.countries.join(', ') : 'UNKNOWN';
  return [
    w('WER?', 'Copernicus Emergency Management Service als Publisher; Erfassungspersonen/Sensoren UNKNOWN', 'BELEGT'),
    w('WEN?', 'UNKNOWN – betroffene Menschen oder Einrichtungen sind nicht identifiziert'),
    w('WEM?', 'Öffentlicher Aktivierungsdatensatz; LAGEFADEN zeigt ihn einer prüfenden Person', 'BELEGT'),
    w('WESSEN?', 'Quellenangabe: Copernicus Emergency Management Service (© 2026 European Union), ' + result.activationCode, 'BELEGT'),
    w('WAS?', result.title + ' · öffentliche Aktivierung ' + result.activationCode, 'BELEGT'),
    w('WANN?', 'Ereignis ' + result.eventTime + ' · Aktivierung ' + result.activationTime + ' · Änderungen ' + result.mappingUpdateTime + ' / ' + result.rapidUpdateTime, 'BELEGT'),
    w('WIE LANGE?', lagHours.toFixed(1) + ' Stunden vom angegebenen Ereigniszeitpunkt zur Aktivierung; Dauer des Ereignisses UNKNOWN', 'ABGELEITET'),
    w('WIE OFT?', '2 API-Ansichten · 1 Aktivierung · ' + result.productCountMapping + ' / ' + result.productCountRapid + ' gemeldete Produkte; keine Zahl unabhängiger Messungen', 'BELEGT'),
    w('WO?', 'Länderfeld: ' + countries + ' · Ortsbezug im Titel: ' + result.title + '; genaue Schadensfläche UNKNOWN', countries === 'UNKNOWN' ? 'UNKNOWN' : 'BELEGT'),
    w('WOHER?', snapshot.mappingList.url + ' · ' + snapshot.rapidList.url, 'BELEGT'),
    w('WOHIN?', 'Minimierter lokaler Snapshot → LAGEFADEN → menschliche Prüfung', 'BELEGT'),
    w('WIE?', 'Zwei offizielle API-Ansichten werden über Aktivierungscode, Titel und Aktivierungszeit verglichen', 'BELEGT'),
    w('WARUM?', 'UNKNOWN – Ursache der Flut wird nicht aus den Metadaten hergeleitet'),
    w('WESHALB?', result.updatesMatch ? 'Gleicher Aktivierungscode und gleiche Änderungszeit' : 'Gleicher Aktivierungscode, aber verschiedene Änderungszeiten → prüfen', 'ABGELEITET'),
    w('WOFÜR?', 'Unterschiedliche Katalogstände sichtbar machen, bevor sie als unabhängige Ereignisse gelesen werden', 'BELEGT'),
    w('WOMIT?', 'Zwei offizielle Listen und ein öffentliches Detail, mit Abrufzeiten und SHA-256-Receipts', 'BELEGT'),
    w('WODURCH?', 'Gemeinsamer EMSR-Code bindet die Ansichten; Produktzahl belegt keine Sensorzahl', 'BELEGT'),
    w('WELCHE VERSION?', snapshot.contract + ' · Mapping-Update ' + result.mappingUpdateTime + ' · Rapid-Update ' + result.rapidUpdateTime, 'BELEGT'),
    w('WIE SICHER?', 'Aktivierungsidentität quellengebunden; Ausdehnung, Schaden und Sensorprovenienz UNKNOWN', 'BELEGT'),
    w('WAS WENN?', 'Metadatenstände weichen ab: Unterschiede offen anzeigen, nicht automatisch zusammenziehen', 'BELEGT'),
    w('WIE WEITER?', 'Öffentliche Revisionsgeschichte und zugehörige Produkte quellengebunden prüfen', 'BELEGT'),
    w('WAS FEHLT?', 'Ausdehnung, Betroffene, Messkette, Produktrevisionen und kausale Erklärung')
  ];
}

