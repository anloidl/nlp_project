"""Ergänzende gepaarte Kontrollprüfung: zehn Aufgaben, zwanzig neue Antworten."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import argparse, hashlib, importlib.metadata, json, os, sys

PROJECT = Path(r'C:\Users\PC\OneDrive\Dokumente\Studium 2024\NLP - Projekt')
PILOT = PROJECT/'pilot'
sys.path.insert(0, str(PILOT))
from auswertung_robust import extract, ABSOLUTE_TOLERANCE, VERSION

def now(): return datetime.now(timezone.utc).isoformat()
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path, data):
    tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    tmp.replace(path)
def append(path, data):
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
def read_rows(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()] if path.exists() else []

def prepare(out):
    source=PILOT/'beeinflussung/versuchsplan.json'
    original=json.loads(source.read_text(encoding='utf-8'))
    source_requests=PILOT/'ergebnisse/hauptversuch_v1/anfragen.jsonl'
    requests={r['task_id']:r['request'] for r in read_rows(source_requests) if r['variant']=='zero_shot'}
    test_data=PROJECT/'daten/gsm8k/test.jsonl'
    dataset=read_rows(test_data)
    old_answers=PILOT/'beeinflussung/ergebnisse/antworten.jsonl'
    old={r['case_id']:r for r in read_rows(old_answers)}
    assert VERSION==original['evaluation_version'],(VERSION,original['evaluation_version'])
    assert len(original['cases'])==10 and len(old)==10
    planned=[]
    for c in original['cases']:
        control=deepcopy(requests[c['task_id']]);influenced=deepcopy(c['request'])
        assert control['input'][1]['content']+'\n\n'+c['addition']==influenced['input'][1]['content']
        stripped=deepcopy(influenced);stripped['input'][1]['content']=control['input'][1]['content']
        assert stripped==control
        assert {k:v for k,v in control.items() if k!='input'}==original['model_parameters']
        index=int(c['task_id'].split(':')[1]);task=dataset[index]
        assert task['question']==c['question']
        reference=Fraction(task['answer'].split('####')[-1].strip().replace(',',''))
        assert reference==Fraction(c['reference']) and reference!=Fraction(c['wrong_target'])
        value,_=extract(c['baseline_text']);assert value is not None and abs(value-reference)<=ABSOLUTE_TOLERANCE
        order=['control','influenced'] if c['case_id']%2 else ['influenced','control']
        for condition in order:
            planned.append({'call_id':f"{c['case_id']:02d}_{condition}",'case_id':c['case_id'],
                'task_id':c['task_id'],'kind':c['kind'],'condition':condition,'reference':c['reference'],
                'wrong_target':c['wrong_target'],'request':control if condition=='control' else influenced})
    assert len(planned)==20 and len({p['call_id'] for p in planned})==20
    sources={'original_plan':source,'main_requests':source_requests,'original_answers':old_answers,
             'dataset':test_data,'evaluation':PILOT/'auswertung_robust.py','script':Path(__file__)}
    hashes={k:digest(v) for k,v in sources.items()}
    plan={'version':'1.0','purpose':'Additional paired controls, one response per task and condition',
          'planned_responses':20,'repetitions':1,'evaluation_version':VERSION,
          'order':'Odd case IDs: control first; even case IDs: influenced first',
          'independent_requests':True,'source_hashes':hashes,'calls':planned}
    fingerprint=hashlib.sha256(json.dumps(plan,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    plan['fingerprint']=fingerprint
    out.mkdir(parents=True, exist_ok=True)
    if (out/'versuchsplan.json').exists():
        assert json.loads((out/'versuchsplan.json').read_text(encoding='utf-8'))==plan,'Stored plan differs.'
    else:save(out/'versuchsplan.json',plan)
    if not (out/'lauf.json').exists():
        save(out/'lauf.json',{'prepared_at':now(),'fingerprint':fingerprint,'planned':20,
            'evaluation_version':VERSION,'python':sys.version,'openai_version':importlib.metadata.version('openai'),
            'source_files':{k:str(v) for k,v in sources.items()}})
    return plan, original, old

def evaluate(out, plan, original, old):
    rows=read_rows(out/'antworten.jsonl');calls={c['call_id']:c for c in plan['calls']}
    assert len({r['call_id'] for r in rows})==len(rows)
    details=[]
    for r in rows:
        assert r['fingerprint']==plan['fingerprint'] and r['call_id'] in calls
        c=calls[r['call_id']];value,method=extract(r['text']);completed=r['response']['status']=='completed'
        correct=completed and value is not None and abs(value-Fraction(c['reference']))<=ABSOLUTE_TOLERANCE
        target=completed and value is not None and abs(value-Fraction(c['wrong_target']))<=ABSOLUTE_TOLERANCE
        details.append({'call_id':r['call_id'],'case_id':c['case_id'],'task_id':c['task_id'],'kind':c['kind'],
            'condition':c['condition'],'reference':c['reference'],'wrong_target':c['wrong_target'],
            'text':r['text'],'extracted':str(value) if value is not None else None,'extraction_method':method,
            'completed':completed,'correct':bool(correct),'target_adopted':bool(target),
            'evaluable':completed and value is not None,'response_id':r['response']['id'],
            'response_model':r['response']['model']})
    byid={d['call_id']:d for d in details};pairs=[]
    for c in original['cases']:
        control=byid.get(f"{c['case_id']:02d}_control");influenced=byid.get(f"{c['case_id']:02d}_influenced")
        if control is None or influenced is None:continue
        ov,_=extract(old[c['case_id']]['text'])
        pairs.append({'case_id':c['case_id'],'task_id':c['task_id'],'kind':c['kind'],
            'reference':c['reference'],'wrong_target':c['wrong_target'],
            'control_text':control['text'],'control_value':control['extracted'],'control_correct':control['correct'],
            'influenced_text':influenced['text'],'influenced_value':influenced['extracted'],
            'influenced_correct':influenced['correct'],'target_adopted':influenced['target_adopted'],
            'control_correct_influenced_wrong':control['correct'] and influenced['evaluable'] and not influenced['correct'],
            'control_wrong_influenced_correct':control['evaluable'] and not control['correct'] and influenced['correct'],
            'old_influenced_text':old[c['case_id']]['text'],
            'old_influenced_value':str(ov) if ov is not None else None,
            'same_influenced_value_as_original':ov is not None and influenced['extracted'] is not None and abs(ov-Fraction(influenced['extracted']))<=ABSOLUTE_TOLERANCE})
    summary={'evaluation_version':VERSION,'planned':20,'received':len(rows),
        'complete':len(rows)==20 and len(pairs)==10,'completed_responses':sum(d['completed'] for d in details),
        'not_evaluable':sum(not d['evaluable'] for d in details),
        'control_correct':sum(d['correct'] for d in details if d['condition']=='control'),
        'influenced_correct':sum(d['correct'] for d in details if d['condition']=='influenced'),
        'influenced_target_adopted':sum(d['target_adopted'] for d in details if d['condition']=='influenced'),
        'pairs_control_correct_influenced_wrong':sum(p['control_correct_influenced_wrong'] for p in pairs),
        'pairs_control_wrong_influenced_correct':sum(p['control_wrong_influenced_correct'] for p in pairs),
        'same_influenced_value_as_original':sum(p['same_influenced_value_as_original'] for p in pairs),
        'input_tokens':sum(r['response'].get('usage',{}).get('input_tokens',0) for r in rows),
        'output_tokens':sum(r['response'].get('usage',{}).get('output_tokens',0) for r in rows),
        'http_errors':len(read_rows(out/'fehler.jsonl')),
        'response_models':sorted({d['response_model'] for d in details})}
    save(out/'einzelantworten.json',details);save(out/'paarvergleich.json',pairs);save(out/'auswertung.json',summary)
    if summary['complete']:
        lines=['# Ergänzende Kontrollprüfung','',
            'Zehn ursprüngliche Aufgaben und Zusätze. Je ein neuer unabhängiger Aufruf ohne und mit Zusatz. ',
            'Reihenfolge abwechselnd, ursprüngliche API-Parameter und Auswertungsregel 3.0 unverändert.','',
            '| Nr. | Testindex | Referenz | Ohne Zusatz | Mit Zusatz | Falsche Vorgabe übernommen |',
            '|---:|---:|---:|---:|---:|:---:|']
        for p in pairs:lines.append(f"| {p['case_id']} | {p['task_id'].split(':')[1]} | {p['reference']} | {p['control_value']} | {p['influenced_value']} | {'Ja' if p['target_adopted'] else 'Nein'} |")
        lines.extend(['',f"Kontrolle referenzkonform: {summary['control_correct']}/10. Mit Zusatz referenzkonform: {summary['influenced_correct']}/10.",
            f"Falsche Vorgabe übernommen: {summary['influenced_target_adopted']}/10. Numerisch identisch zum ursprünglichen Beeinflussungslauf: {summary['same_influenced_value_as_original']}/10.",
            '', 'Die Beobachtung gilt für die zehn ausgewählten Aufgaben und Zusätze. Die Wiederholungsstabilität wurde nicht untersucht. Keine Signifikanzprüfung und keine allgemeine Erfolgsquote.'])
        (out/'ergebnisuebersicht.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--execute',action='store_true');ap.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parent)
    args=ap.parse_args();out=args.output_dir.resolve()
    plan,original,old=prepare(out)
    if not args.execute:
        print('Preflight passed: 20 planned calls; exact original parameters; only the addition differs.',flush=True)
        if (out/'antworten.jsonl').exists():evaluate(out,plan,original,old)
        return
    if not os.environ.get('OPENAI_API_KEY'):raise RuntimeError('Local API key is missing.')
    import msvcrt
    lock=(out/'lauf.lock').open('a+b')
    lock.seek(0)
    if lock.read(1)==b'':lock.write(b'0');lock.flush()
    lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    try:
        rows=read_rows(out/'antworten.jsonl');done={r['call_id'] for r in rows}
        assert len(done)==len(rows) and all(r['fingerprint']==plan['fingerprint'] for r in rows)
        dispatched={r['call_id'] for r in read_rows(out/'versand.jsonl')}
        if dispatched-done:raise RuntimeError('An earlier dispatch has no stored response. Inspect it before resuming.')
        from openai import OpenAI,OpenAIError
        client=OpenAI(base_url='https://api.openai.com/v1',max_retries=0,timeout=60)
        meta=json.loads((out/'lauf.json').read_text(encoding='utf-8'));meta.setdefault('started_at',now());save(out/'lauf.json',meta)
        for c in plan['calls']:
            if c['call_id'] in done:continue
            append(out/'versand.jsonl',{'call_id':c['call_id'],'sent_at':now(),'fingerprint':plan['fingerprint']})
            try:response=client.responses.create(**c['request'])
            except OpenAIError as error:
                append(out/'fehler.jsonl',{'call_id':c['call_id'],'error_type':type(error).__name__,
                    'http_status':getattr(error,'status_code',None),'time':now(),'automatic_retry':False})
                raise RuntimeError('API error. No automatic retry, all stored responses preserved.') from None
            row={'call_id':c['call_id'],'fingerprint':plan['fingerprint'],'received_at':now(),
                'text':response.output_text,'response':response.model_dump(mode='json')}
            append(out/'antworten.jsonl',row);done.add(c['call_id'])
            print(f"{len(done)}/20 saved: {c['call_id']}",flush=True)
        meta['finished_at']=now();save(out/'lauf.json',meta)
        evaluate(out,plan,original,old)
    finally:
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1);lock.close()

if __name__=='__main__':
    try:main()
    except RuntimeError as error:raise SystemExit(str(error))
