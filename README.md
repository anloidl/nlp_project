# NLP-Projekt – mathematische Textaufgaben

Experimente zu Aufgabenstellung 2 im IU-Kurs DLBAIPNLP01_D. Aufgaben, Prompts und Antworten sind auf Englisch. Bericht, allgemeines Projektprotokoll und Literaturprüfung werden separat geführt.

## Aufbau

| Ordner | Inhalt |
| --- | --- |
| `daten/gsm8k/` | 7.473 Trainings- und 1.319 Testaufgaben; Herkunft und Prüfsummen in `manifest.json` |
| `pilot/` | Skripte, Konfigurationen, Prompt-Versionen und Ergebnisse des Hauptversuchs: 1.319 Aufgaben × drei Prompts = 3.957 Antworten |
| `zusatzstudie/` | 300 gemeinsame Testaufgaben × drei Prompts × drei Modellbedingungen = 2.700 Antworten; Auswahl in `auswahl.json` |
| `pilot/beeinflussung/` | Zehn zuvor richtige Zero-Shot-Antworten mit irreführenden Zusätzen |
| `fehleranalyse/` | Auswahlplan und qualitative Sichtung von 30 Nichttreffern; keine Scorekorrekturen |
| `mcnemar/` | Zusätzliche exakte, zweiseitige McNemar-Auswertung und Ergebnisse |

GSM8K stammt aus [openai/grade-school-math](https://github.com/openai/grade-school-math), Commit `3101c7d5072418e28b9008a6636bde82a006892c`. Die Trainingsdatei liefert drei Demonstrationen (Indizes 0–2) und technische Pilotaufgaben (3–22 sowie 23–25). Es fand kein Modelltraining statt; ein eigener Validierungssatz wurde nicht angelegt. Die Zusatzstichprobe ist Teil des Testsatzes, Auswahlstartwert `2026110801`. Referenzlösungen der Zielaufgaben wurden nicht an das Modell gesendet.

## Einrichtung

Windows PowerShell im Repository-Hauptordner; ursprünglich Python 3.12.14 und OpenAI-SDK 3.46.0:

```powershell
py -3.12 -m venv .venv
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install -r .\pilot\requirements-lock.txt
```

Nur für McNemar zusätzlich `& $py -m pip install scipy`. Die historische SciPy-Version ist nicht dokumentiert; die neu verwendete Version separat festhalten. Ursprüngliche Lock-Dateien nicht überschreiben.

## Ergebnisse ohne API-Aufrufe nachrechnen

Ein API-Schlüssel ist nicht erforderlich. Die vollständigen gespeicherten Laufdateien müssen vorhanden sein.

```powershell
# Hauptversuch: neue Auswertung unter pruefung/
& $py .\pilot\auswertung_robust.py --run .\pilot\ergebnisse\hauptversuch_v1 --output .\pruefung\hauptversuch

# Zusatzstudie: bestehende Auswertungsdateien neu schreiben
& $py -c "import sys; sys.path.insert(0, 'zusatzstudie'); import fortsetzen as f; s=f.studie; out,req,ref,_=s.prepare('studie'); s.evaluate(out,req,ref)"

# Beeinflussung und optionale Statistik: bestehende Auswertungen neu schreiben
& $py .\pilot\beeinflussung\beeinflussung.py
& $py .\mcnemar\mcnemar.py
```

Maßgeblich ist **Bewertung 3.0**: `auswertung_v3.json` im Hauptversuch und `auswertung.json` in der Zusatzstudie. Die Hauptversuchs-Neuauswertung benötigt zusätzlich `einzelfaelle_v2.json` für den Vergleich mit der ursprünglichen Regel. Die Zusatzstudie wird über `fortsetzen.py` eingebunden, damit Tausenderkommas in Referenzzahlen korrekt eingelesen werden.

Accuracy ist der Anteil referenzkonformer Endwerte, absolute Toleranz `1e-9`. Nicht extrahierbare oder unvollständige Antworten zählen als Nichttreffer. Regel 3.0 entstand nach Sichtung von Testantworten; die Zusatzstudie ist explorativ. Nicht jeder Nichttreffer ist ein Rechenfehler.

## Neue Modellaufrufe

Nur `--execute` aktiviert **kostenpflichtige API-Aufrufe**. Dafür `OPENAI_API_KEY` lokal als Umgebungsvariable setzen, niemals einchecken. `.env` wird nicht automatisch geladen.

- Hauptversuch: `pilot/experiment.py --phase main --output neue_laeufe/hauptversuch --execute`. Für einen technischen Pilot `--phase pilot` verwenden. Danach zuerst `pilot/auswertung.py --output ...`, anschließend die robuste Auswertung auf denselben Lauf anwenden.
- Zusatzstudie: `zusatzstudie/fortsetzen.py --phase pilot --execute`, danach `--phase studie --execute`. Der Studienstart prüft den abgeschlossenen Pilot automatisch.
- Beeinflussung: `pilot/beeinflussung/beeinflussung.py --execute`.

Die letzten beiden Skripte haben feste Ergebnisordner und überspringen gespeicherte Antworten. Für unabhängige neue Läufe eine separate Arbeitskopie mit neuem Ergebnisbereich verwenden. Historische Antworten nicht löschen.

Im Hauptversuch: `gpt-6-luna`, Reasoning `none`, Temperatur 0, `top_p=1`, 1.024 Ausgabetokens. In der Zusatzstudie: Luna `none`, Luna `low`, `gpt-6.1-sol` `low`; Temperatur und `top_p` jeweils weggelassen, gemeinsames Limit 32.768 Tokens einschließlich Reasoning. Daher wurde auch Luna `none` neu ausgeführt. Alle Anfragen sind unabhängig, ohne Werkzeuge und mit `store=false`.

## Nachvollziehbarkeit

Rohantworten stehen in `antworten.jsonl`, Anfragen in `anfragen.jsonl`, Metadaten in `lauf.json`, Einzelbewertungen in `einzelfaelle*.json`. Eingefrorene Aufbauten und Prüfsummen sichern den damaligen Stand. `fortsetzen.py` ergänzt die ursprüngliche Zusatzstudie um Referenznormalisierung und Wiederholungen bei Dateisperren. Eine erneute Generierung garantiert keine identischen Antworten. Historische Dateien nicht verändern und Fingerabdruckprüfungen nicht umgehen.
