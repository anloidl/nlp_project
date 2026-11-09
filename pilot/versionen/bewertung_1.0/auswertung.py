"""Lokale Auswertung; keine Modellaufrufe."""
import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import re
from experiment import ROOT, VARIANTS, read_jsonl, write_json


def extract_final(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    markers = [line for line in lines if line.startswith('FINAL:')]
    if len(markers) != 1 or not lines or markers[0] != lines[-1]:
        return None
    match = re.fullmatch(r'FINAL: ([+-]?[0-9]+(?:\.[0-9]+)?)', lines[-1])
    return Decimal(match[1]) if match else None


def evaluate(output):
    metadata = json.loads((output / 'lauf.json').read_text(encoding='utf-8'))
    references = json.loads((output / 'referenzen.json').read_text(encoding='utf-8'))
    requests = read_jsonl(output / 'anfragen.jsonl')
    expected = {(row['task_id'], row['variant']) for row in requests}
    if len(expected) != 60 or len(requests) != 60:
        raise ValueError('Pilotplan muss genau 60 eindeutige Anfragen enthalten.')
    counts = {variant: Counter() for variant in VARIANTS}
    seen, details = set(), []
    for row in read_jsonl(output / 'antworten.jsonl'):
        key = (row['task_id'], row['variant'])
        if key not in expected or key in seen or row['fingerprint'] != metadata['fingerprint']:
            raise ValueError('Unerwartete, doppelte oder fremde Antwort.')
        seen.add(key)
        value = extract_final(row['text'])
        completed = row['response']['status'] == 'completed'
        correct = completed and value is not None and value == Decimal(references[row['task_id']])
        count = counts[row['variant']]
        count['received'] += 1
        count['correct'] += int(correct)
        count['format_errors'] += int(value is None)
        count['incomplete_outputs'] += int(not completed)
        for token_type in ('input_tokens', 'output_tokens', 'total_tokens'):
            count[token_type] += (row['response'].get('usage') or {}).get(token_type, 0) or 0
        details.append({'task_id': key[0], 'variant': key[1], 'extracted': str(value) if value is not None else None,
                        'reference': references[key[0]], 'completed': completed, 'correct': correct})
    summary = {'phase': 'technical_pilot', 'complete': seen == expected, 'expected': 60, 'received': len(seen),
               'missing': [list(key) for key in sorted(expected - seen)], 'variants': {}}
    for variant in VARIANTS:
        count = counts[variant]
        summary['variants'][variant] = {
            **dict(count), 'planned': 20, 'missing': 20 - count['received'],
            'accuracy': count['correct'] / 20 if summary['complete'] else None,
        }
    write_json(output / 'auswertung.json', summary)
    write_json(output / 'einzelfaelle.json', details)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'ergebnisse' / 'pilot_v1')
    args = parser.parse_args()
    result = evaluate(args.output)
    print(f'Pilot: {result["received"]}/60 Antworten; vollständig: {result["complete"]}.')
    print('Ergebnisse in auswertung.json. Pilotwerte sind keine Hauptversuchsergebnisse.')
