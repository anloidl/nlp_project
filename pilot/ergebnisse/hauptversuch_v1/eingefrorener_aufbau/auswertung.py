"""Lokale Auswertung; keine Modellaufrufe."""
import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import re
from experiment import ROOT, VARIANTS, read_jsonl, write_json

EVALUATION_VERSION = '2.0-number-fallback'
NUMBER_PATTERN = r'[+-]?[0-9]+(?:\.[0-9]+)?'


def extract_answer(text):
    """Ergebnis und Extraktionsweg; ohne FINAL nur eine vollständige Zahlenantwort."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if text.count('FINAL:') == 1 and lines:
        match = re.fullmatch(r'FINAL: (' + NUMBER_PATTERN + ')', lines[-1])
        if match:
            return Decimal(match[1]), 'final'
    if 'FINAL:' not in text and re.fullmatch(NUMBER_PATTERN, text.strip()):
        return Decimal(text.strip()), 'number_fallback'
    return None, 'unextractable'


def extract_final(text):
    return extract_answer(text)[0]


def evaluate(output):
    metadata = json.loads((output / 'lauf.json').read_text(encoding='utf-8'))
    references = json.loads((output / 'referenzen.json').read_text(encoding='utf-8'))
    requests = read_jsonl(output / 'anfragen.jsonl')
    expected = {(row['task_id'], row['variant']) for row in requests}
    phase = metadata['phase']
    planned_per_variant = 1319 if phase == 'main' else 20
    split = 'test' if phase == 'main' else 'train'
    indices = range(1319) if phase == 'main' else range(3, 23)
    required = {(f'{split}:{i}', variant) for i in indices for variant in VARIANTS}
    if expected != required or len(requests) != len(required):
        raise ValueError('Anfrageplan entspricht nicht der festgelegten Versuchsphase.')
    if set(references) != {task_id for task_id, _ in required}:
        raise ValueError('Referenzaufgaben stimmen nicht mit dem Anfrageplan überein.')
    counts = {variant: Counter() for variant in VARIANTS}
    seen, details = set(), []
    for row in read_jsonl(output / 'antworten.jsonl'):
        key = (row['task_id'], row['variant'])
        if key not in expected or key in seen or row['fingerprint'] != metadata['fingerprint']:
            raise ValueError('Unerwartete, doppelte oder fremde Antwort.')
        seen.add(key)
        value, extraction = extract_answer(row['text'])
        completed = row['response']['status'] == 'completed'
        correct = completed and value is not None and value == Decimal(references[row['task_id']])
        count = counts[row['variant']]
        count['received'] += 1
        count['correct'] += int(correct)
        count['format_errors'] += int(extraction != 'final')
        count['number_fallback'] += int(extraction == 'number_fallback')
        count['unextractable'] += int(value is None)
        count['incomplete_outputs'] += int(not completed)
        for token_type in ('input_tokens', 'output_tokens', 'total_tokens'):
            count[token_type] += (row['response'].get('usage') or {}).get(token_type, 0) or 0
        details.append({'task_id': key[0], 'variant': key[1], 'extracted': str(value) if value is not None else None,
                        'reference': references[key[0]], 'completed': completed, 'correct': correct,
                        'extraction': extraction, 'format_compliant': extraction == 'final'})
    summary = {'phase': phase, 'evaluation_version': EVALUATION_VERSION,
               'complete': seen == expected, 'expected': len(required), 'received': len(seen),
               'missing': [list(key) for key in sorted(expected - seen)], 'variants': {}}
    for variant in VARIANTS:
        count = counts[variant]
        summary['variants'][variant] = {
            **dict(count), 'planned': planned_per_variant, 'missing': planned_per_variant - count['received'],
            'accuracy': count['correct'] / planned_per_variant if summary['complete'] else None,
            'format_compliance': (count['received'] - count['format_errors']) / planned_per_variant if summary['complete'] else None,
        }
    # Neue Dateinamen erhalten die ursprünglichen strengen Pilot-Auswertungen.
    write_json(output / 'auswertung_v2.json', summary)
    write_json(output / 'einzelfaelle_v2.json', details)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'ergebnisse' / 'pilot_v1')
    args = parser.parse_args()
    result = evaluate(args.output)
    print(f'{result["phase"]}: {result["received"]}/{result["expected"]} Antworten; vollständig: {result["complete"]}.')
    print('Ergebnisse in auswertung_v2.json. Pilotwerte sind keine Hauptversuchsergebnisse.')
