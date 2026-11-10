# Technischer Pilot

Vorbereitet für GPT-6 Luna mit `reasoning.effort="none"`. 20 englische Aufgaben (`train:3` bis `train:22`), drei Prompt-Varianten, insgesamt 60 Modellaufrufe. Die ersten drei Trainingsaufgaben stehen als Beispiele in Few-Shot und CoT. Keine Testaufgabe dient als Pilotaufgabe. IDs sind nullbasiert.

## Ziel

API-Zugang, Nachrichtenformat, Extraktion, Ausgabelimit, Speicherung und Wiederaufnahme prüfen. Pilot-Accuracy wird nur zur technischen Kontrolle berechnet; sie ist kein Testergebnis des Hauptversuchs. Keine Auswahl von Modell oder Prompts anhand möglichst großer Accuracy-Unterschiede.

## Einrichtung unter Windows

Im Ordner `pilot` mit Python 3.10 oder neuer:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip freeze > requirements-lock.txt
```

Falls `python` nicht gefunden wird, eine vorhandene Python-Installation auswählen. Die Abhängigkeit ist vor dem ersten Installieren noch nicht auf eine Version festgeschrieben; `requirements-lock.txt` hält danach die tatsächlich installierten Versionen fest. Für Wiederholung dieselben Versionen installieren. Die Run-Metadaten erfassen zusätzlich die verwendete SDK-Version.

## Vorbereitung ohne Modellaufrufe

```powershell
python experiment.py
python auswertung.py
```

Die Vorbereitung benötigt nur die Python-Standardbibliothek. Sie prüft die GSM8K-Dateien gegen das vorhandene Datenmanifest und erzeugt unter `ergebnisse/pilot_v1` 60 vollständige Anfragen sowie separate lokale Referenzwerte und Laufmetadaten. Ohne empfangene Antworten meldet die Auswertung einen unvollständigen Lauf mit 60 fehlenden Antworten, keine Accuracy.

## API-Schlüssel und tatsächlicher Start

`OPENAI_API_KEY` muss lokal als Umgebungsvariable verfügbar sein. Den Schlüssel nicht in diese Dateien, ins Repository oder in den Chat schreiben. Das Programm liest ausschließlich diese Variable für die Authentifizierung und sendet Anfragen an `https://api.openai.com/v1`. Kontozugriff und Abrechnung müssen eingerichtet sein. Nach der Einrichtung die folgenden Befehle mit der Python-Datei aus `.venv` ausführen:

```powershell
.\.venv\Scripts\python.exe experiment.py --execute
.\.venv\Scripts\python.exe auswertung.py
```

Erst `--execute` führt kostenpflichtige Modellaufrufe aus. Ohne diesen Schalter wird ausschließlich lokal vorbereitet. Keine Werkzeuge und kein fortlaufender Chat werden an die API übergeben. Referenzwerte der Zielaufgaben werden nicht mitgesendet.

## Speicherung, Fehler und Wiederaufnahme

Antworten werden sofort einzeln in `antworten.jsonl` gespeichert, einschließlich vollständiger API-Antwort, Modellkennung, Status, Zeitstempel und Tokenverbrauch. Bei Verbindungsproblemen oder vorübergehenden Serverfehlern sind höchstens drei technische Wiederholungen nach 2/4/8 Sekunden vorgesehen. Bei Verbindungsabbrüchen ist unklar, ob serverseitig bereits eine Antwort erzeugt wurde; das wird protokolliert und kann zusätzliche Kosten verursachen. Fehlermeldungen enthalten keine Schlüssel oder vollständigen API-Fehlertexte.

Ein erneuter Start mit `--execute` überspringt bereits gespeicherte Antworten. Auch mathematisch falsche, formal ungültige oder abgeschnittene empfangene Antworten werden nicht erneut generiert. Ändern sich Konfiguration, Prompts oder Skripte, muss ein neuer Ausgabeordner angegeben werden, z. B. `--output ergebnisse/pilot_v2`. Bei beschädigter JSONL-Datei bricht das Programm zur manuellen Prüfung ab. Nicht zwei Prozesse gleichzeitig im selben Ausgabeordner starten.

## Bewertung und technische Abnahme

Die letzte nichtleere Antwortzeile muss genau einmal `FINAL: <Zahl>` enthalten. Zahlen werden mit Decimal exakt verglichen. Ungültige Formate und unvollständige Modellantworten gelten als nicht korrekt und werden gesondert gezählt. Technisch fehlende Antworten sind keine Mathematikfehler; solange Antworten fehlen, wird keine vollständige Pilot-Accuracy ausgewiesen.

Vor dem Hauptversuch prüfen:

- Alle 60 Antworten vorhanden und ohne Änderung von Modell/Effort erzeugt?
- API akzeptiert alle vorgesehenen Parameter?
- Sämtliche Formatfehler und abgeschnittene Antworten geprüft; reicht das gemeinsame Tokenlimit?
- Stichprobe der extrahierten Zahlen und Bewertungen mit den Rohantworten abgeglichen?
- Prompts, Parameter, Parser und tatsächlich installierte Pakete endgültig dokumentiert?

Die Skripte starten keinen Hauptversuch und keine Beeinflussungsprüfung. Ihr Umfang ist bewusst auf den technischen Pilot begrenzt. Ein erfolgreicher lokaler Probelauf ersetzt keinen Test des tatsächlichen API-Zugriffs.

API-Grundlage: [OpenAI Python-Quickstart](https://developers.openai.com/api/docs/quickstart), [Responses API](https://developers.openai.com/api/reference/python/resources/responses/methods/create), geprüft am 07.11.2026.


## Eingerichteter Stand und Schlüsselverwaltung

Python 3.12.14 ist in `.venv` eingerichtet, OpenAI-SDK 3.46.0 installiert und mit `pip check` geprüft. `requirements-lock.txt` enthält alle tatsächlich installierten Paketversionen. Die Umgebung basiert auf der auf diesem Rechner verfügbaren Codex-Python-Laufzeit; für einen anderen Rechner Python 3.12 installieren und die Umgebung aus der Lock-Datei neu erstellen. Ohne Aktivierung kann `.\.venv\Scripts\python.exe` direkt verwendet werden.

Ein Schlüssel ist bereits als Windows-Benutzervariable `OPENAI_API_KEY` vorhanden. Dessen Wert wird weder in Projektdateien noch im Chat gespeichert. Für einen neuen oder ersetzten Schlüssel:

1. In Windows nach „Umgebungsvariablen für dieses Konto bearbeiten“ suchen.
2. Unter „Benutzervariablen“ den Eintrag `OPENAI_API_KEY` neu anlegen oder bearbeiten.
3. Den eigenen Schlüssel aus dem OpenAI-API-Dashboard als Wert einfügen und mit OK bestätigen.
4. Neue PowerShell öffnen; bereits gestartete Anwendungen wie Codex gegebenenfalls neu starten, damit sie die Änderung übernehmen.

Die Windows-Benutzervariable ist dauerhaft, aber kein verschlüsselter Passwortspeicher. Sie liegt außerhalb des OneDrive-Projektordners. Das SDK liest den Schlüssel aus der Umgebung. Keine `.env`-Datei im synchronisierten Projektordner erforderlich.

API-Schlüssel verwalten: https://platform.openai.com/api-keys
Offizielle Anleitung: https://developers.openai.com/api/docs/quickstart

## Zweiter technischer Pilot

Pilot v1 mit Prompt-Version 0.2 enthält 60 echte Antworten. Dabei fehlte bei 8 Zero-Shot- und 15 Few-Shot-Antworten das vorgeschriebene Format. Keine Ausgaben waren abgeschnitten. Für Prompt-Version 0.3 wurde ausschließlich bei P1 und P2 die Aufforderung zum Format `FINAL: <number>` ausdrücklich wiederholt; Systemnachricht, CoT-Prompt, Beispiele, Zielaufgaben und Modellparameter sind unverändert. Die Formatänderung dient der technischen Einhaltung, nicht der Optimierung mathematischer Ergebnisse.

Die alten Rohdaten bleiben unter `ergebnisse/pilot_v1` erhalten. Für die neue Version verwenden:

```powershell
.\.venv\Scripts\python.exe experiment.py --execute --output ergebnisse/pilot_v2
.\.venv\Scripts\python.exe auswertung.py --output ergebnisse/pilot_v2
```

Im Ausgabeordner von v1 darf mit dem neuen Prompt-Fingerabdruck nicht fortgesetzt werden. Ohne `--output` verwenden die Skripte weiterhin den ursprünglichen Ordner `pilot_v1`; deshalb für Version 0.3 die obigen vollständigen Befehle benutzen. Alle Angaben zu Pilotwerten bleiben von der Testauswertung auf den 1.319 Aufgaben getrennt.


## Festgelegte Bewertung 2.0 und Hauptversuch

Die IU-Aufgabenstellung verlangt Accuracy, kein FINAL-Präfix. Deshalb getrennte Bewertung:

- Genau eine gültige FINAL-Endzeile: Zahlenwert auswerten.
- Kein FINAL-Präfix und gesamte Antwort ist eine einzelne Zahl: Zahlen-Fallback.
- Sonst nicht extrahierbar; keine beliebige Zahl aus einem Rechenweg übernehmen.
- Gleicher Decimal-Vergleich für alle Varianten; Formateinhaltung separat berichten.

Die Originalauswertung bleibt erhalten. Neue Auswertung in `auswertung_v2.json` und `einzelfaelle_v2.json`. Frühere Abschnitte dieser Anleitung zur ausschließlich strengen Bewertung beschreiben Version 1.0 und sind damit ersetzt. Frühere Skriptversionen liegen im Versionsordner.

Nach erfolgreicher Pilotprüfung ist der Hauptversuch mit Prompt 0.3 und Bewertung 2.0 freigegeben:

```powershell
.\.venv\Scripts\python.exe experiment.py --phase main --execute --output ergebnisse/hauptversuch_v1
.\.venv\Scripts\python.exe auswertung.py --output ergebnisse/hauptversuch_v1
```

3.957 Anfragen, jeweils alle 1.319 Testaufgaben pro Variante. Zum reinen Vorbereiten `--execute` weglassen. Für Auswertungen eines laufenden Experiments zuerst eine ruhende Datenkopie verwenden oder das Ende abwarten. Nicht mehrere Experiment-Prozesse im selben Laufordner starten. Nach einer Unterbrechung denselben Startbefehl bei unverändertem Aufbau ausführen; gespeicherte Antworten werden übersprungen. Keinen anderen Modellnamen als Ersatz einsetzen. Bei einem Fehler nach den dokumentierten technischen Wiederholungen hält der Prozess an.

Datensatz, Nachrichten, Code und Paketversionen vor dem ersten Hauptaufruf gesichert. Das Programm läuft zunächst sequenziell; bei mehreren tausend Anfragen ist entsprechend Wartezeit einzuplanen. Ein gestarteter Lauf ist noch kein abgeschlossenes Ergebnis.


## Aktueller Auswertungsstand 3.0 und abgeschlossene Beeinflussungsprüfung

Seit 08.11.2026 gilt die ausdrücklich übernommene robuste automatische Auswertung 3.0. Alle bisherigen Rohantworten wurden damit neu bewertet. Keine manuellen Ergänzungen. Die vorangehenden Abschnitte zu Auswertung 1.0/2.0 dokumentieren die Historie; für aktuelle Resultate gilt `auswertung_robust.py` und je Lauf `auswertung_v3.json`. `bewertungsstand.json` kennzeichnet die aktuelle Version. Die Hauptversuchs-Konfiguration, Originalantworten und alten Auswertungen bleiben unverändert.

```powershell
.\.venv\Scripts\python.exe auswertung_robust.py --run ergebnisse/hauptversuch_v1 --output ergebnisse/hauptversuch_v1
```

Aktuelle Haupt-Accuracy: Zero-Shot 65,13 %, Few-Shot 64,52 %, CoT 95,68 %. Die Änderung wurde nach Sichtung von Hauptantworten entwickelt; dieser Umstand steht ausdrücklich im Bericht. Ein neuer Modelllauf wurde dafür nicht benötigt.

Maßgeblich ist die abschließende Beeinflussungsprüfung vom 10.11.2026 unter `beeinflussung/kontrollpruefung_20261110/`. Dieselben zehn Aufgaben und Zusätze wurden mit unveränderten Hauptversuchsparametern erneut geprüft. Pro Aufgabe gab es einen neuen Kontrollaufruf ohne Zusatz und einen mit Zusatz, in wechselnder Reihenfolge. Alle 20 Antworten sind vollständig und auswertbar. Ohne Zusatz sind 10/10 Antworten referenzkonform, mit Zusatz 3/10. Sieben Antworten übernehmen genau den falschen Vorgabewert. Jede Bedingung wurde pro Aufgabe einmal ausgeführt, die Wiederholungsstabilität wurde nicht untersucht.

Die portable Nachrechnung benötigt keinen API-Schlüssel und verändert keine gespeicherten Versuchsdaten. Im Repository-Hauptordner: `python pilot/beeinflussung/auswertung_kontrollpruefung.py`. Die Ergebnisse und der Prüfnachweis werden nach `pruefung/kontrollpruefung_20261110/` geschrieben.

Der frühere Beeinflussungslauf mit sechs Übernahmen liegt unverändert unter `beeinflussung/ergebnisse/`. Das dazugehörige `beeinflussung.py` und `beeinflussungsprotokoll.md` dokumentieren die Historie. Für die aktuelle Ergebnisdarstellung gilt der abschließende Kontrolllauf. Die gesonderte Modellvergleichsstudie ist unter `../zusatzstudie/` dokumentiert.
