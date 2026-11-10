"""Gespeicherte Kontrollprüfung portabel prüfen und nachrechnen, ohne API-Zugriff."""
from pathlib import Path
from fractions import Fraction
from copy import deepcopy
from datetime import datetime, timezone
import argparse, hashlib, json, sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'pilot'))
from auswertung_robust import extract, ABSOLUTE_TOLERANCE, VERSION

def load(path):return json.loads(path.read_text(encoding='utf-8'))
def lines(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()] if path.exists() else []
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def require(ok,reason):
    if not ok:raise ValueError(reason)
def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def evaluate(run,out):
    require(run.is_dir(),'Laufordner fehlt.')
    require(out!=run and run not in out.parents,'Ausgabe darf nicht im gespeicherten Lauf liegen.')
    plan=load(run/'versuchsplan.json');meta=load(run/'lauf.json')
    fingerprint=plan['fingerprint'];unsigned={k:v for k,v in plan.items() if k!='fingerprint'}
    require(hashlib.sha256(json.dumps(unsigned,sort_keys=True,ensure_ascii=False).encode()).hexdigest()==fingerprint,'Plan-Fingerabdruck stimmt nicht.')
    require(meta['fingerprint']==fingerprint and plan['evaluation_version']==VERSION,'Lauf- oder Auswertungsversion stimmt nicht.')
    # Resolve known sources relative to this checkout. Recorded absolute Windows paths
    # are provenance only and are never used to open files on another machine.
    sources={'original_plan':ROOT/'pilot/beeinflussung/versuchsplan.json',
        'main_requests':ROOT/'pilot/ergebnisse/hauptversuch_v1/anfragen.jsonl',
        'original_answers':ROOT/'pilot/beeinflussung/ergebnisse/antworten.jsonl',
        'dataset':ROOT/'daten/gsm8k/test.jsonl','evaluation':ROOT/'pilot/auswertung_robust.py',
        'script':run/'kontrollpruefung.py'}
    require(set(sources)==set(plan['source_hashes']),'Unerwartete Quellnachweise.')
    for key,path in sources.items():require(path.is_file() and digest(path)==plan['source_hashes'][key],f'Quellpruefsumme abweichend: {key}')
    original=load(sources['original_plan']);cases={c['case_id']:c for c in original['cases']}
    old={r['case_id']:r for r in lines(sources['original_answers'])}
    main={r['task_id']:r['request'] for r in lines(sources['main_requests']) if r['variant']=='zero_shot'}
    tasks=lines(sources['dataset']);calls=plan['calls']
    require(len(cases)==10 and len(old)==10 and len(calls)==20 and plan['repetitions']==1,'Erwartet werden zehn Aufgaben und 20 Aufrufe.')
    expected_order=[]
    for case_id,c in cases.items():
        for condition in (['control','influenced'] if case_id%2 else ['influenced','control']):
            expected_order.append(f'{case_id:02d}_{condition}')
        task=tasks[int(c['task_id'].split(':')[1])]
        require(task['question']==c['question'],'Aufgabentext abweichend.')
        require(Fraction(task['answer'].split('####')[-1].strip().replace(',',''))==Fraction(c['reference']),'Referenz abweichend.')
    require([c['call_id'] for c in calls]==expected_order,'Reihenfolge abweichend.')
    for c in calls:
        orig=cases[c['case_id']]
        expected=main[orig['task_id']] if c['condition']=='control' else orig['request']
        require(c['request']==expected,'Anfrage entspricht nicht dem Original.')
        require(all(c[k]==orig[k] for k in ['task_id','reference','wrong_target','kind']),'Fallzuordnung abweichend.')
        require(c['request']=={**original['model_parameters'],'input':c['request']['input']},'API-Parameter abweichend.')
        control=main[orig['task_id']];influenced=deepcopy(orig['request'])
        require(control['input'][1]['content']+'\n\n'+orig['addition']==influenced['input'][1]['content'],'Zusatz abweichend.')
        influenced['input'][1]['content']=control['input'][1]['content']
        require(influenced==control,'Bedingungen unterscheiden sich ausserhalb des Zusatzes.')
    rows=lines(run/'antworten.jsonl');dispatch=lines(run/'versand.jsonl')
    require(len(rows)==20 and len(dispatch)==20,'Unvollstaendiger Lauf.')
    require([r['call_id'] for r in rows]==[r['call_id'] for r in dispatch]==expected_order,'Antwort- oder Versandzuordnung abweichend.')
    require(len({r['response']['id'] for r in rows})==20,'Doppelte Antwortkennung.')
    details=[]
    for c,r in zip(calls,rows):
        response=r['response']
        require(r['fingerprint']==fingerprint and response['status']=='completed','Unvollstaendige oder falsch zugeordnete Antwort.')
        require(response['model']==c['request']['model'],'Modellkennung abweichend.')
        for key in ['temperature','top_p','max_output_tokens','store']:
            require(response[key]==c['request'][key],f'Bestaetigter Parameter abweichend: {key}')
        require(response['reasoning']['effort']==c['request']['reasoning']['effort'],'Reasoning abweichend.')
        echoed=''.join(v['text'] for item in response['output'] if item.get('type')=='message' for v in item['content'] if v.get('type')=='output_text')
        require(echoed==r['text'],'Gespeicherter Antworttext stimmt nicht mit Rohantwort ueberein.')
        value,method=extract(r['text']);completed=response['status']=='completed'
        correct=completed and value is not None and abs(value-Fraction(c['reference']))<=ABSOLUTE_TOLERANCE
        target=completed and value is not None and abs(value-Fraction(c['wrong_target']))<=ABSOLUTE_TOLERANCE
        details.append({'call_id':r['call_id'],'case_id':c['case_id'],'task_id':c['task_id'],'kind':c['kind'],
            'condition':c['condition'],'reference':c['reference'],'wrong_target':c['wrong_target'],
            'text':r['text'],'extracted':str(value) if value is not None else None,'extraction_method':method,
            'completed':completed,'correct':bool(correct),'target_adopted':bool(target),
            'evaluable':completed and value is not None,'response_id':response['id'],'response_model':response['model']})
    byid={r['call_id']:r for r in details};pairs=[]
    for case_id,c in cases.items():
        control=byid[f'{case_id:02d}_control'];influenced=byid[f'{case_id:02d}_influenced'];ov,_=extract(old[case_id]['text'])
        pairs.append({'case_id':case_id,'task_id':c['task_id'],'kind':c['kind'],'reference':c['reference'],'wrong_target':c['wrong_target'],
            'control_text':control['text'],'control_value':control['extracted'],'control_correct':control['correct'],
            'influenced_text':influenced['text'],'influenced_value':influenced['extracted'],'influenced_correct':influenced['correct'],
            'target_adopted':influenced['target_adopted'],
            'control_correct_influenced_wrong':control['correct'] and influenced['evaluable'] and not influenced['correct'],
            'control_wrong_influenced_correct':control['evaluable'] and not control['correct'] and influenced['correct'],
            'old_influenced_text':old[case_id]['text'],'old_influenced_value':str(ov) if ov is not None else None,
            'same_influenced_value_as_original':ov is not None and influenced['extracted'] is not None and abs(ov-Fraction(influenced['extracted']))<=ABSOLUTE_TOLERANCE})
    summary={'evaluation_version':VERSION,'planned':20,'received':20,'complete':True,
        'completed_responses':sum(d['completed'] for d in details),'not_evaluable':sum(not d['evaluable'] for d in details),
        'control_correct':sum(d['correct'] for d in details if d['condition']=='control'),
        'influenced_correct':sum(d['correct'] for d in details if d['condition']=='influenced'),
        'influenced_target_adopted':sum(d['target_adopted'] for d in details if d['condition']=='influenced'),
        'pairs_control_correct_influenced_wrong':sum(p['control_correct_influenced_wrong'] for p in pairs),
        'pairs_control_wrong_influenced_correct':sum(p['control_wrong_influenced_correct'] for p in pairs),
        'same_influenced_value_as_original':sum(p['same_influenced_value_as_original'] for p in pairs),
        'input_tokens':sum(r['response'].get('usage',{}).get('input_tokens',0) for r in rows),
        'output_tokens':sum(r['response'].get('usage',{}).get('output_tokens',0) for r in rows),
        'http_errors':len(lines(run/'fehler.jsonl')),'response_models':sorted({d['response_model'] for d in details})}
    for name,value in [('einzelantworten.json',details),('paarvergleich.json',pairs),('auswertung.json',summary)]:
        require(load(run/name)==value,f'Nachrechnung weicht von {name} ab.')
    out.mkdir(parents=True,exist_ok=True)
    save(out/'einzelantworten.json',details);save(out/'paarvergleich.json',pairs);save(out/'auswertung.json',summary)
    save(out/'pruefung.json',{'checked_at':datetime.now(timezone.utc).isoformat(),'passed':True,
        'read_only_sources':True,'api_calls':0,'source_hashes_verified':True,'stored_results_match':True,
        'plan_fingerprint':fingerprint,'raw_answers_sha256':digest(run/'antworten.jsonl')})
    print(json.dumps(summary,ensure_ascii=False));print(f'Nachrechnung stimmt ueberein. Ausgabe: {out}')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',type=Path,default=Path(__file__).resolve().parent/'kontrollpruefung_20261110')
    ap.add_argument('--output',type=Path,default=ROOT/'pruefung/kontrollpruefung_20261110')
    args=ap.parse_args();evaluate(args.run.resolve(),args.output.resolve())
if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,FileNotFoundError) as error:raise SystemExit(f'Pruefung fehlgeschlagen: {error}')
