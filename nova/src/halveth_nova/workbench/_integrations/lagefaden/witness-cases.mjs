// SPDX-License-Identifier: MIT
const at = minutes => `2026-10-27T10:${String(minutes).padStart(2,'0')}:00Z`;
const e = (id,nodeId,kind,minute,observedAt=null,refId=null,claim=null) => ({id,nodeId,kind,at:at(minute),observedAt,refId,claim});
const a=e('A1','A','OBSERVATION',2,at(1),null,'possibly_blocked');
const b=e('B1','B','FORWARD',3,null,'A1');
const reaction=e('B2','B','REACTION',4,null,'B1');
const peer=e('C1','C','PEER_ACTION_OBSERVATION',5,at(4),'B2');
const old=e('C2','C','OBSERVATION',6,'2026-10-26T10:00:00Z',null,'free');
const packet=(caseId,events,reviewAvailable=true)=>({caseId,routeId:'AID_ROUTE_DEMO',startsAt:at(0),endsAt:at(10),
  freshnessMinutes:60,reviewAvailable,nodes:['A','B','C'],events});
export const witnessCases = [
  {id:'STALE_VIEW',title:'Die Weitergabe und die alte Gegensicht',
    story:'Nach einem erfundenen Unwetter wird ein Hilfsweg geprüft. A meldet ein mögliches Hindernis. B gibt A weiter und reagiert darauf. C sieht Bs Reaktion – und hat eine eigene Sicht von gestern.',
    packet:packet('STALE_VIEW',[a,b,reaction,peer,old]),
    expected:{ownRouteObservations:2,forwardedReports:1,peerSignals:2,reviewState:'GAP_REVIEW'},
    authorNote:'Zwei angegebene Ursprungssichten, davon eine alt. Reaktion und beobachtete Reaktion bestätigen den Wegzustand nicht.'},
  {id:'CURRENT_CONFLICT',title:'C sieht den Weg jetzt anders',
    story:'Nur eine Änderung: Cs eigene Sicht stammt jetzt von heute. Der Gegensatz zu A wird dadurch aktuell.',
    packet:packet('CURRENT_CONFLICT',[a,b,reaction,peer,{...old,observedAt:at(5)}]),
    expected:{ownRouteObservations:2,forwardedReports:1,peerSignals:2,reviewState:'CONFLICT_REVIEW'},
    authorNote:'Ein aktueller Widerspruch braucht Klärung. Mehr Kopien entscheiden ihn nicht.'},
  {id:'MISSING_ORIGIN',title:'Eine Weitergabe ohne ihren Ursprung',
    story:'B meldet eine Weitergabe. Der Ursprungsbeleg fehlt im übergebenen Paket. Bs Reaktion liefert ihn nicht nach.',
    packet:packet('MISSING_ORIGIN',[{...b,refId:null},reaction,peer,old]),
    expected:{ownRouteObservations:1,forwardedReports:1,peerSignals:2,reviewState:'PROVENANCE_REVIEW'},
    authorNote:'Die Herkunftslücke bleibt ausdrücklich sichtbar; die ungebundene Weitergabe zählt nicht als eigene Sichtung.'},
  {id:'VIEW_RECOVERY',title:'Sicht verloren. Wieder da. Was ist neu?',
    story:'Cs Sicht fällt aus. Danach wird die Sicht als wiederhergestellt gemeldet. Erst eine zusätzliche eigene Beobachtung bringt einen neuen Wegbefund.',
    packet:packet('VIEW_RECOVERY',[a,b,e('C0','C','VIEW_LOST',4),e('C1','C','VIEW_RESTORED',6),
      e('C2','C','OBSERVATION',8,at(7),null,'free')]),
    expected:{ownRouteObservations:2,forwardedReports:1,peerSignals:0,reviewState:'CONFLICT_REVIEW'},
    authorNote:'Wiederherstellung allein schließt keine Beobachtungslücke. Der neue Befund widerspricht A.'},
  {id:'REVIEW_STOP',title:'Die menschliche Prüfung ist nicht besetzt',
    story:'Die Meldungen sind dieselben. Heute ist jedoch keine prüfende Person verfügbar. Eine automatische Wegfreigabe entsteht dadurch nicht.',
    packet:packet('REVIEW_STOP',[a,b,reaction,peer,old],false),
    expected:{ownRouteObservations:2,forwardedReports:1,peerSignals:2,reviewState:'REVIEWER_UNAVAILABLE'},
    authorNote:'Stop betrifft hier den Prüfarbeitsablauf. Das Modell sendet keinen Steuer- oder Flugstopp.'},
  {id:'HIDDEN_DEPENDENCE',title:'Drei Namen beweisen keine Unabhängigkeit',
    story:'A, B und C geben eigene aktuelle Sichtungen an. Ihre Aussagen passen zusammen. Wer ihre Kennungen tatsächlich kontrolliert, ist aus dem Paket nicht erkennbar.',
    packet:packet('HIDDEN_DEPENDENCE',[a,e('B1','B','OBSERVATION',3,at(2),null,'possibly_blocked'),
      e('C1','C','OBSERVATION',4,at(3),null,'possibly_blocked')]),
    expected:{ownRouteObservations:3,forwardedReports:0,peerSignals:0,reviewState:'HUMAN_REVIEW'},
    authorNote:'Für dieses Gegenbeispiel legt der Fallautor einen gemeinsamen Controller fest. Diese Autoreninformation wird nicht in den Prüfer eingespeist. Er kann den versteckten Zusammenhang nicht erkennen.'}
];
