# Willkommen bei TradeLoop

Öffnen Sie unten einen Abschnitt. Über **Anleitung** gelangen Sie jederzeit zurück.

**Start:** Projekte → Demo-Nutzer wählen → Demoprojekt laden → `demo2026` eingeben → Angebote oder Kundenfeedback öffnen. Zuerst simulierte Daten verwenden.

**Bewertungsablauf:** Importieren → analysieren → Originaltext prüfen → Problem bestätigen → Aufgabe veröffentlichen → Belege einreichen → abnehmen → spätere Bewertungen vergleichen.

## 1 · Projekte

**Zweck:** Nutzer und Projekt für die weitere Arbeit auswählen.

1. Lokalen Demo-Nutzer wählen; für Leitungsaufgaben die Projektleitung auswählen.
2. Demoprojekt laden oder auswählen und mit `demo2026` öffnen.
3. Nutzer, Projekt und Rolle in der Seitenleiste prüfen.
4. Für eigene Arbeit Nutzer und Projekt mit Produkt, Märkten und Zugangscode erstellen. Der Ersteller wird Projektleitung.
5. Die Projektleitung fügt bestehende Nutzer mit Rollen hinzu.

**Prüfen:** Projekt und verfügbare Aktionen müssen zur Rolle passen. Leere Listen können auf fehlende Mitgliedschaft hinweisen. Ein Code gewährt keine Mitgliedschaft. Die lokale Nutzerauswahl dient der Demo und ist keine produktive Anmeldung.

## 2 · Lieferantenangebote

**Vorbereitung:** CSV-Vorlage oder `data/demo/supplier_quotes.csv`. Beliebige Excel/PDF-Dateien werden hier nicht verarbeitet.

1. Hochladen, Vorschau und Validierung prüfen, Import bestätigen.
2. Angebotsgruppe im Vergleich wählen. Preise, Mindestmengen, Lieferzeit und Zahlung prüfen.
3. Gewichtung ändern und Rangfolge nachvollziehen.
4. Originalzeilen und Rückfragen ansehen.
5. Die Projektleitung entscheidet mit Begründung.

**Prüfen:** Risiken müssen auf Originalfelder verweisen. Die Rangfolge unterstützt Entscheidungen. Fehlende Fracht oder Steuern erlauben keine vollständigen Gesamtkosten. Fehlende Spalten oder unterschiedliche Währungen zuerst klären; Wechselkurse nicht erfinden. Doppelte Dateien nicht erneut importieren.

## 3 · Aufgaben und Tagesberichte

**Vorbereitung:** Veröffentlichte Aufgabe. Falls keine vorhanden ist, im Kundenfeedback ein Problem bestätigen und eine Aufgabe veröffentlichen.

1. Zuständige Rolle liest Abnahmekriterien und Abhängigkeiten.
2. Status ändern: `todo` = offen, `doing` = in Arbeit, `blocked` = blockiert.
3. Ergebnis beschreiben und prüfbare Unterlagen oder Referenzen angeben.
4. Zur Abnahme einreichen. Einreichen bedeutet noch nicht abgeschlossen.
5. Die Projektleitung prüft und akzeptiert oder fordert mit Begründung Ergänzungen. Rollen- und Prüfgrenzen gelten.

Tagesberichte mit Aufgaben verknüpfen und Arbeit, Referenzen, Hindernisse und nächste Schritte notieren. Die Fortschrittsprüfung zeigt Verzögerungen und fehlende Unterlagen. Berichte ersetzen keine Abnahmebelege; fehlende Berichte beweisen keine schlechte Leistung.

**Prüfen:** Abschluss erst nach Abnahme. Bei gesperrten Aktionen Veröffentlichung, Rolle, Unterlagen und Prüfberechtigung kontrollieren.

## 4 · Kundenfeedback

**Vorbereitung:** CSV; zum Üben simulierte `reviews_before.csv` und `reviews_after.csv` unter `data/demo/`.

1. Datei hochladen, Gruppe benennen und importieren.
2. Regelbasierte oder konfigurierte KI-Analyse auswählen.
3. Einmal starten und warten. KI sendet erforderliche Bewertungsfelder an den Anbieter und kann Kosten verursachen.
4. Probleme öffnen, Anzahl, Originaltext und fehlende Informationen prüfen.
5. Bestätigen, überarbeiten und bestätigen oder begründet verwerfen.
6. Aufgabe entwerfen und veröffentlichen lassen; unter Aufgaben bearbeiten und abnehmen.
7. Spätere Bewertungen importieren, Ausgangsgruppe, Folgegruppe und Thema wählen und vergleichen.

**Prüfen:** Anzahl, Anteile und Stichprobengröße gemeinsam lesen. Bewertungsanteile sind keine Produktausfallraten; Rückgänge allein beweisen keine Wirkung. Ohne zuverlässige Zuordnung keine Lieferantenverantwortung behaupten. Duplikate werden übersprungen. Bei KI-Fehlern auf regelbasierte Ersatzanalyse achten. Technische Details sind optional.

## 5 · Inhalte und Prüfung

**Aktuelle Seite:** Manuelle V1, Feedback und manuelle V2 sowie unabhängige Regelprüfung. Modellgenerierung und zwei Überarbeitungen sind im Backend getestet, aber noch nicht hier angebunden. Es gibt derzeit keinen automatischen V3-Button.

1. US-Englisch oder Deutsch wählen und manuelle V1 speichern.
2. V1 wählen, Änderungswünsche und überarbeiteten Text eingeben, manuelle V2 speichern.
3. Verlauf und Unterschiede ansehen. Bestehende V2 wird nicht überschrieben.
4. In der Regelprüfung Markt und Szenario wählen, Titel oder Vertragstext einfügen und prüfen.
5. Risiko, Fundstelle, Vorschlag und Quelle/Version kontrollieren, Text ändern und erneut prüfen.

**Prüfen:** Plattformrichtlinien, Verbraucherinformationen und interne Einkaufsstandards unterscheiden. Kein Treffer bedeutet keine umfassende Konformität. Fehlende Abdeckung manuell prüfen. Die Anzeigesprache übersetzt keine Produkttexte; Zielmarkt separat auswählen.

## 6 · Einstellungen

Vereinfachtes Chinesisch, Englisch oder Deutsch wählen. Noch nicht übersetzte Hinweise erscheinen auf Chinesisch. Originalbelege und gespeicherte Daten bleiben unverändert.

Funktioniert DeepSeek lokal, diese Konfiguration beibehalten. Zum Wechsel Anbieter, API-Adresse und Modellname aus der Kontoverwaltung übernehmen, zugehörigen Schlüssel eingeben und anwenden. Speichern sendet keine Anfrage; erst die nächste Analyse nutzt die Einstellungen. Mit kleinen, nicht sensiblen Daten testen. Nur DeepSeek wurde online geprüft; andere Einträge separat verifizieren.

Über die Wiederherstellung zur lokalen `.env` zurückkehren. Einstellungen gelten nur für die Browsersitzung und können danach verloren gehen. Schlüssel nicht in Chats oder Screenshots teilen. Bei Fehlern Zugriff, Modell, Adresse, Guthaben und Netzwerk prüfen.

## 7 · Begriffe und Zusammenarbeit

Belege sind Originalaufzeichnungen. Probleme brauchen manuelle Prüfung. Aufgabenentwürfe sind noch nicht veröffentlicht. Folgeprüfungen beweisen keine Kausalität. Person A pflegt Dienste, Daten, KI und Rechte; Person B Seiten, Anleitung und Demo. Code teilen, aber keine Datenbanken, Schlüssel oder virtuellen Umgebungen.
