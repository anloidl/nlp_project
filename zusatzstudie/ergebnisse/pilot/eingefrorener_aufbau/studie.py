"""Separate, resumable supplementary study; no changes to the original main study."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from datetime import datetime, timezone
from fractions import Fraction
from collections import defaultdict
from openai import OpenAI, APIConnectionError, APITimeoutError, RateLimitError, InternalServerError
from auswertung_robust import extract, ABSOLUTE_TOLERANCE

ROOT = Path(__file__).resolve().parent
VARIANTS = ['zero_shot', 'few_shot', 'cot']

def now(): return datetime.now(timezone.utc).isoformat()
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def rows(p): return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x.strip()] if p.exists() else []
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, x):
    tmp = p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(x, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    tmp.replace(p)
def append(p, x):
    with p.open('a', encoding='utf-8') as f:
        f.write(json.dumps(x, ensure_ascii=False)+'\n'); f.flush(); os.fsync(f.fileno())

def prepare(phase):
    config, prompts, selection = (read(ROOT/f) for f in ['config.json','prompts.json','auswahl.json'])
    split = 'train' if phase=='pilot' else 'test'
    datafile = ROOT.parent/'daten'/'gsm8k'/f'{split}.jsonl'
    assert sha(datafile)==config['data_sha256'][split], 'Dataset hash mismatch'
    data = rows(datafile)
    indices = selection['pilot_train_indices'] if phase=='pilot' else selection['test_indices']
    assert len(indices)==len(set(indices)) and len(indices)==(3 if phase=='pilot' else 300)
    conditions=config['conditions']
    requests=[]; references={}
    for pos, index in enumerate(indices):
        item=data[index]; references[str(index)]=item['answer'].split('####')[-1].strip()
        for offset in range(3):
            ci=(pos+offset)%3; condition=conditions[ci]
            for voffset in range(3):
                variant=VARIANTS[(pos+ci+voffset)%3]
                payload=dict(model=condition['model'], reasoning={'effort':condition['effort']},
                    max_output_tokens=config['max_output_tokens'], store=False,
                    input=[{'role':'system','content':prompts['system']},
                           {'role':'user','content':prompts[variant].replace('{question}',item['question'])}])
                assert not any(k in payload for k in ['temperature','top_p','tools','previous_response_id'])
                requests.append(dict(key=f'{index}:{condition["id"]}:{variant}', index=index,
                    condition=condition['id'], variant=variant, payload=payload))
    files=['studie.py','auswertung_robust.py','config.json','prompts.json','auswahl.json','requirements-lock.txt']
    fingerprint=hashlib.sha256(json.dumps({'files':{f:sha(ROOT/f) for f in files},'phase':phase},sort_keys=True).encode()).hexdigest()
    out=ROOT/'ergebnisse'/phase; out.mkdir(parents=True,exist_ok=True)
    plan={'phase':phase,'fingerprint':fingerprint,'planned':len(requests),'dataset_sha256':sha(datafile)}
    if (out/'lauf.json').exists():
        assert read(out/'lauf.json')['fingerprint']==fingerprint, 'Frozen run changed; aborting'
        assert rows(out/'anfragen.jsonl')==requests
    else:
        write(out/'lauf.json', dict(plan, prepared_at=now()))
        write(out/'referenzen.json',references)
        for request in requests: append(out/'anfragen.jsonl',request)
        snap=out/'eingefrorener_aufbau'; snap.mkdir()
        for f in files: shutil.copy2(ROOT/f,snap/f)
    return out, requests, references, config

def evaluate(out, requests, references):
    answers=rows(out/'antworten.jsonl'); expected={r['key']:r for r in requests}
    assert len({a['key'] for a in answers})==len(answers), 'Duplicate responses'
    assert all(a['key'] in expected for a in answers)
    groups=defaultdict(lambda:dict(received=0,correct=0,unextractable=0,incomplete=0,input_tokens=0,output_tokens=0,reasoning_tokens=0))
    details=[]
    for a in answers:
        req=expected[a['key']]; value,method=extract(a['text']); target=Fraction(references[str(req['index'])])
        complete=a['response']['status']=='completed'
        correct=complete and value is not None and abs(value-target)<=ABSOLUTE_TOLERANCE
        group=groups[f'{req["condition"]}/{req["variant"]}']; group['received']+=1; group['correct']+=int(correct)
        group['unextractable']+=int(value is None); group['incomplete']+=int(not complete)
        usage=a['response'].get('usage') or {}
        for k in ['input_tokens','output_tokens']: group[k]+=usage.get(k,0)
        group['reasoning_tokens']+=(usage.get('output_tokens_details') or {}).get('reasoning_tokens',0)
        details.append(dict(key=a['key'],target=str(target),extracted=str(value) if value is not None else None,method=method,correct=correct))
    for name,g in groups.items():
        n=sum(1 for r in requests if f'{r["condition"]}/{r["variant"]}'==name)
        g['planned']=n; g['accuracy']=g['correct']/n if g['received']==n else None
    summary=dict(updated_at=now(),planned=len(requests),received=len(answers),complete=len(answers)==len(requests),groups=dict(groups))
    write(out/'auswertung.json',summary); write(out/'einzelfaelle.json',details)
    return summary

def gate():
    out, requests, references, config=prepare('pilot')
    summary=evaluate(out,requests,references)
    assert summary['complete'], 'Pilot not complete'
    for a in rows(out/'antworten.jsonl'):
        req=next(r for r in requests if r['key']==a['key'])
        resp=a['response']
        assert resp['status']=='completed' and a['text'].strip(), 'Pilot incomplete or empty'
        assert resp['model']==req['payload']['model'], 'Unexpected returned model'
        assert resp['reasoning']['effort']==req['payload']['reasoning']['effort'], 'Unexpected reasoning effort'
        assert resp['usage']['output_tokens']<config['max_output_tokens']//2, 'Pilot has insufficient token headroom'
    result=dict(passed=True,checked_at=now(),pilot_fingerprint=read(out/'lauf.json')['fingerprint'],responses=len(requests),checks=['27 complete nonempty responses','requested model and effort returned','no temperature/top_p/tools/history sent','output tokens below half the shared limit','unique complete nine-cell schedule'])
    write(ROOT/'technische_pruefung.json',result)
    return result

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--phase',choices=['pilot','studie'],default='pilot'); parser.add_argument('--execute',action='store_true'); parser.add_argument('--gate',action='store_true')
    args=parser.parse_args()
    if args.gate: print(json.dumps(gate(),ensure_ascii=False)); return
    out,requests,references,config=prepare(args.phase)
    if not args.execute: print(json.dumps(dict(phase=args.phase,planned=len(requests),prepared=True))); return
    if args.phase=='studie': gate()
    answers=rows(out/'antworten.jsonl'); evaluate(out,requests,references)
    done={a['key'] for a in answers}
    client=OpenAI(max_retries=0,timeout=240)
    def status(state): write(out/'prozessstatus.json',dict(state=state,pid=os.getpid(),updated_at=now(),received=len(done),planned=len(requests)))
    status('running')
    try:
        for req in requests:
            if req['key'] in done: continue
            for attempt in range(4):
                start=time.monotonic()
                try:
                    response=client.responses.create(**req['payload']); break
                except (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError) as exc:
                    append(out/'api_fehler.jsonl',dict(key=req['key'],at=now(),attempt=attempt+1,type=type(exc).__name__))
                    if attempt==3: raise
                    time.sleep(2**(attempt+1))
            append(out/'antworten.jsonl',dict(key=req['key'],at=now(),seconds=time.monotonic()-start,text=response.output_text,response=response.model_dump(mode='json')))
            done.add(req['key']); status('running')
            if len(done)%9==0: evaluate(out,requests,references); print(f'{args.phase}: {len(done)}/{len(requests)}',flush=True)
        evaluate(out,requests,references); status('completed')
    except Exception as exc:
        status('failed'); print(type(exc).__name__,flush=True); raise

if __name__=='__main__': main()
