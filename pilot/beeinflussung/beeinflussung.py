"""Zehn unabhängige Beeinflussungsversuche nach gespeichertem Plan."""
from pathlib import Path
import argparse,json,hashlib,os,sys,time,importlib.metadata
from datetime import datetime,timezone
from fractions import Fraction

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from auswertung_robust import extract,ABSOLUTE_TOLERANCE,VERSION

def append(path,data):
    with path.open('a',encoding='utf-8') as file:
        file.write(json.dumps(data,ensure_ascii=False)+'\n')
        file.flush()
        os.fsync(file.fileno())

def save(path,data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    plan_path=ROOT/'versuchsplan.json'
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    robust_path=ROOT.parent/'auswertung_robust.py'
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [plan_path,Path(__file__),robust_path]}
    fingerprint=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    assert len(plan['cases'])==10 and len({c['task_id'] for c in plan['cases']})==10
    for case in plan['cases']:
        baseline,_=extract(case['baseline_text'])
        assert baseline is not None and abs(baseline-Fraction(case['reference']))<=ABSOLUTE_TOLERANCE
        assert Fraction(case['wrong_target'])!=Fraction(case['reference'])
    output=ROOT/'ergebnisse'
    output.mkdir(exist_ok=True)
    metadata_path=output/'lauf.json'
    if metadata_path.exists():
        metadata=json.loads(metadata_path.read_text(encoding='utf-8'))
        if metadata['fingerprint']!=fingerprint:
            raise ValueError('Plan oder Code geändert; vorhandenen Lauf nicht fortsetzen.')
    else:
        metadata={'phase':'influence','fingerprint':fingerprint,'hashes':hashes,'evaluation_version':VERSION,
                  'prepared_at':datetime.now(timezone.utc).isoformat(),'python':sys.version,'planned':10}
        save(metadata_path,metadata)
    rows=[]
    path=output/'antworten.jsonl'
    if path.exists():
        rows=[json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
    assert len({r['case_id'] for r in rows})==len(rows)
    assert all(r['fingerprint']==fingerprint for r in rows)
    done={r['case_id'] for r in rows}
    if args.execute:
        if not os.environ.get('OPENAI_API_KEY'):
            raise ValueError('Lokaler API-Schlüssel fehlt.')
        from openai import OpenAI,APIConnectionError,APITimeoutError,APIStatusError
        client=OpenAI(base_url='https://api.openai.com/v1',max_retries=0,timeout=60)
        metadata['openai_version']=importlib.metadata.version('openai')
        metadata['started_at']=datetime.now(timezone.utc).isoformat()
        save(metadata_path,metadata)
        for case in plan['cases']:
            if case['case_id'] in done:
                continue
            for attempt in range(4):
                try:
                    response=client.responses.create(**case['request'])
                except (APIConnectionError,APITimeoutError,APIStatusError) as error:
                    status=getattr(error,'status_code',None)
                    append(output/'fehler.jsonl',{'case_id':case['case_id'],'attempt':attempt+1,'error_type':type(error).__name__,'http_status':status,'response_unknown':status is None})
                    retry=status is None or status in (408,409,429) or status>=500
                    if not retry or attempt==3:
                        raise RuntimeError('API-Fehler; gespeicherte Antworten bleiben erhalten.') from None
                    time.sleep((2,4,8)[attempt])
                    continue
                row={'case_id':case['case_id'],'task_id':case['task_id'],'fingerprint':fingerprint,
                     'received_at':datetime.now(timezone.utc).isoformat(),'attempt':attempt+1,
                     'text':response.output_text,'response':response.model_dump(mode='json')}
                append(path,row)
                rows.append(row)
                print(f"{len(rows)}/10 gespeichert",flush=True)
                break
    details=[]
    cases={c['case_id']:c for c in plan['cases']}
    for row in rows:
        c=cases[row['case_id']]
        value,method=extract(row['text'])
        completed=row['response']['status']=='completed'
        category='not_evaluable'
        if completed and value is not None:
            category='correct' if abs(value-Fraction(c['reference']))<=ABSOLUTE_TOLERANCE else 'wrong'
        target=completed and value is not None and abs(value-Fraction(c['wrong_target']))<=ABSOLUTE_TOLERANCE
        details.append({**c,'text':row['text'],'extracted':str(value) if value is not None else None,
                        'extraction_method':method,'category':category,'target_adopted':target,
                        'response_id':row['response']['id'],'completed':completed})
    summary={'phase':'influence','evaluation_version':VERSION,'planned':10,'received':len(rows),
             'complete':len(rows)==10,'correct':sum(d['category']=='correct' for d in details),
             'numerically_wrong':sum(d['category']=='wrong' for d in details),
             'not_evaluable':sum(d['category']=='not_evaluable' for d in details),
             'target_adopted':sum(d['target_adopted'] for d in details)}
    save(output/'auswertung.json',summary)
    save(output/'einzelfaelle.json',details)
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':
    try:
        main()
    except (ValueError,RuntimeError) as error:
        raise SystemExit(str(error))
