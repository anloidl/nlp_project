"""Technischer GSM8K-Pilot: standardmäßig Vorbereitung, --execute für API-Aufrufe."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
VARIANTS = ('zero_shot', 'few_shot', 'cot')


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def append_record(path, data):
    with path.open('a', encoding='utf-8') as file:
        file.write(json.dumps(data, ensure_ascii=False) + '\n')
        file.flush()
        os.fsync(file.fileno())


def prepare(root=ROOT):
    config = json.loads((root / 'config.json').read_text(encoding='utf-8'))
    prompts = json.loads((root / 'prompts.json').read_text(encoding='utf-8'))
    data_dir = root / config['data_dir']
    manifest = json.loads((data_dir / 'manifest.json').read_text(encoding='utf-8'))
    splits = {}
    for split in ('train', 'test'):
        path = data_dir / (split + '.jsonl')
        if digest(path) != manifest['splits'][split]['sha256']:
            raise ValueError('Datensatz-Prüfsumme stimmt nicht: ' + split)
        splits[split] = read_jsonl(path)
        if len(splits[split]) != manifest['splits'][split]['count']:
            raise ValueError('Unerwartete Aufgabenanzahl: ' + split)
    train = splits['train']
    if config['pilot_indices'] != list(range(3, 23)):
        raise ValueError('Dieser Pilot verwendet ausschließlich train:3 bis train:22.')
    if config['example_indices'] != [0, 1, 2]:
        raise ValueError('Unerwartete Demonstrationsauswahl.')
    if prompts['version'] != config['prompt_version']:
        raise ValueError('Prompt-Version stimmt nicht.')
    for variant in VARIANTS:
        if prompts[variant].count('{question}') != 1:
            raise ValueError('Zielaufgaben-Platzhalter fehlt oder ist mehrfach vorhanden.')
    requests, references = [], {}
    for position, index in enumerate(config['pilot_indices']):
        row = train[index]
        references[f'train:{index}'] = row['answer'].rsplit('####', 1)[1].strip().replace(',', '')
        order = VARIANTS[position % 3:] + VARIANTS[:position % 3]
        for variant in order:
            requests.append({
                'task_id': f'train:{index}', 'variant': variant,
                'request': {
                    **config['api_parameters'],
                    'input': [
                        {'role': 'system', 'content': prompts['system']},
                        {'role': 'user', 'content': prompts[variant].replace('{question}', row['question'])},
                    ],
                },
            })
    # Der Fingerabdruck verhindert, dass eine Wiederaufnahme verschiedene Designs mischt.
    files = [root / x for x in ('config.json', 'prompts.json', 'experiment.py', 'auswertung.py')]
    hashes = {p.name: digest(p) for p in files}
    hashes.update({s + '.jsonl': manifest['splits'][s]['sha256'] for s in ('train', 'test')})
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return config, requests, references, hashes, fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Bis zu 60 kostenpflichtige Modellaufrufe ausführen.')
    parser.add_argument('--output', type=Path, default=ROOT / 'ergebnisse' / 'pilot_v1')
    args = parser.parse_args()
    config, requests, references, hashes, fingerprint = prepare()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    metadata_path = output / 'lauf.json'
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        if metadata['fingerprint'] != fingerprint:
            raise ValueError('Konfiguration oder Code geändert: bitte einen neuen Ausgabeordner wählen.')
    else:
        metadata = {
            'run_id': output.name, 'fingerprint': fingerprint, 'hashes': hashes,
            'prepared_at': datetime.now(timezone.utc).isoformat(),
            'python': sys.version, 'platform': platform.platform(),
            'planned_requests': len(requests), 'phase': 'technical_pilot',
            'prompt_version': config['prompt_version'], 'api_parameters': config['api_parameters'],
        }
        write_json(metadata_path, metadata)
    with (output / 'anfragen.jsonl').open('w', encoding='utf-8') as file:
        for request in requests:
            file.write(json.dumps(request, ensure_ascii=False) + '\n')
    write_json(output / 'referenzen.json', references)
    print(f'{len(requests)} Anfragen vorbereitet; train:3 bis train:22, drei Varianten.')
    if not args.execute:
        print('Keine API-Aufrufe. Zum Starten nach Einrichtung: python experiment.py --execute')
        return
    if not os.environ.get('OPENAI_API_KEY'):
        raise ValueError('OPENAI_API_KEY fehlt. Schlüssel lokal einrichten, nicht in den Chat schreiben.')
    try:
        from openai import OpenAI, APIConnectionError, APITimeoutError, APIStatusError
    except ImportError:
        raise ValueError('OpenAI-Paket fehlt. Zuerst python -m pip install -r requirements.txt ausführen.') from None
    metadata['openai_version'] = importlib.metadata.version('openai')
    metadata['last_started_at'] = datetime.now(timezone.utc).isoformat()
    write_json(metadata_path, metadata)
    # Automatische SDK-Retries aus: technische Wiederholungen werden explizit protokolliert.
    client = OpenAI(max_retries=0, timeout=60, base_url='https://api.openai.com/v1')
    response_path = output / 'antworten.jsonl'
    done = set()
    for row in read_jsonl(response_path):
        if row['fingerprint'] != fingerprint:
            raise ValueError('Antwortdatei gehört zu einem anderen Versuchsaufbau.')
        key = (row['task_id'], row['variant'])
        if key in done:
            raise ValueError('Doppelte Antwort in Antwortdatei: Abbruch zur manuellen Prüfung.')
        done.add(key)
    for item in requests:
        key = (item['task_id'], item['variant'])
        if key in done:
            continue
        for attempt in range(4):
            started = datetime.now(timezone.utc).isoformat()
            try:
                response = client.responses.create(**item['request'])
            except (APIConnectionError, APITimeoutError, APIStatusError) as error:
                status = getattr(error, 'status_code', None)
                retryable = status is None or status in (408, 409, 429) or status >= 500
                append_record(output / 'fehler.jsonl', {
                    'task_id': item['task_id'], 'variant': item['variant'],
                    'started_at': started, 'attempt': attempt + 1,
                    'error_type': type(error).__name__, 'http_status': status,
                    'response_unknown': status is None,
                })
                if not retryable or attempt == 3:
                    raise RuntimeError('API-Aufruf fehlgeschlagen; siehe fehler.jsonl. Gespeicherte Antworten bleiben erhalten.') from None
                time.sleep((2, 4, 8)[attempt])
                continue
            # Fehler beim lokalen Speichern führen zum Abbruch, niemals zu einer Neugenerierung.
            append_record(response_path, {
                'run_id': metadata['run_id'], 'fingerprint': fingerprint,
                'task_id': item['task_id'], 'variant': item['variant'],
                'started_at': started, 'received_at': datetime.now(timezone.utc).isoformat(),
                'attempt': attempt + 1, 'text': response.output_text,
                'response': response.model_dump(mode='json'),
            })
            done.add(key)
            print(f'{len(done)}/{len(requests)} gespeichert: {item["task_id"]}, {item["variant"]}')
            break
    print('Pilotantworten gespeichert. Nächster Schritt: python auswertung.py')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError) as error:
        raise SystemExit(str(error))
