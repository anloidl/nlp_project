"""Übernommene automatische Auswertung 3.0; verändert keine Originaldateien.

Regel 3.0 ist nach Sichtung von Testantworten entwickelt und damit eine nachträgliche
Robustheitsprüfung, keine vorab festgelegte Bestätigungsauswertung.
"""
import argparse
import ast
import hashlib
from collections import Counter
from fractions import Fraction
import json
from pathlib import Path
import re

VERSION = '3.0-automatic-robustness'
ABSOLUTE_TOLERANCE = Fraction(1, 1_000_000_000)
NUM = r'[+-]?(?:(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?'
SCALAR = r'(?:' + NUM + r')(?:\s*/\s*(?:' + NUM + r'))?'
UNITS = r'(?:%|percent|dollars?|minutes?|hours?)'


def parse_scalar(text):
    """Angelsächsische Schreibweise; kein Runden auf ganze Zahlen."""
    s = text.strip().replace('\u2212', '-').replace('\u00a0', ' ')
    # Uhrzeiten nicht auf eine Zahl verkürzen: Das würde AM/PM-Information verlieren.
    match = re.fullmatch(r'[$€£]?\s*(' + SCALAR + r')\s*(?:' + UNITS + r')?\s*[.!]?', s, flags=re.I)
    if not match:
        return None, 'invalid_scalar'
    value = match[1].replace(',', '').replace(' ', '')
    try:
        if '/' in value:
            a,b = value.split('/')
            return Fraction(a)/Fraction(b), 'scalar'
        return Fraction(value), 'scalar'
    except (ValueError, ZeroDivisionError, OverflowError):
        return None, 'invalid_scalar'


def calculate_expression(text):
    """Nur begrenzte Grundrechenoperationen; kein eval und keine Funktionsaufrufe."""
    source = text.strip().replace('×','*').replace('÷','/').replace('−','-')
    if len(source)>200:
        return None
    try:
        tree=ast.parse(source,mode='eval')
        if len(list(ast.walk(tree)))>100:
            return None
        def visit(node):
            if isinstance(node, ast.Constant) and type(node.value) in (int,float):
                token=ast.get_source_segment(source,node)
                if not re.fullmatch(NUM,token):
                    raise ValueError()
                return Fraction(token)
            if isinstance(node, ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
                return visit(node.operand)*(1 if isinstance(node.op,ast.UAdd) else -1)
            if isinstance(node, ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
                a,b=visit(node.left),visit(node.right)
                if isinstance(node.op,ast.Add): return a+b
                if isinstance(node.op,ast.Sub): return a-b
                if isinstance(node.op,ast.Mult): return a*b
                return a/b
            raise ValueError()
        return visit(tree.body)
    except (SyntaxError,ValueError,ZeroDivisionError,OverflowError):
        return None


def parse_final_segment(segment):
    line=segment.strip().splitlines()[0] if segment.strip() else ''
    value,method=parse_scalar(line)
    if value is not None:
        return value,method
    if line.count('=')==1:
        left,right=line.split('=')
        result=calculate_expression(left)
        answer,_=parse_scalar(right)
        if result is not None and answer is not None and abs(result-answer)<=ABSOLUTE_TOLERANCE:
            return answer,'checked_equation'
    # Eine explizite FINAL-Antwort darf vor einem nachfolgenden Erklärungssatz stehen.
    match=re.match(r'^(' + SCALAR + r')\.\s+[A-Za-z]',line)
    if match:
        value,_=parse_scalar(match[1])
        return value,'final_before_explanation'
    return None,'unextractable'


def extract(text):
    # Keine Referenzwerte, Aufgaben-IDs oder bisherigen Bewertungen in der Extraktion.
    parts=re.split(r'FINAL\s*:',text,flags=re.I)
    if len(parts)>1:
        parsed=[parse_final_segment(s) for s in parts[1:]]
        if all(v is not None for v,m in parsed) and len({v for v,m in parsed})==1:
            return parsed[-1][0], 'repeated_consistent_final' if len(parsed)>1 else parsed[0][1]
        return None,'ambiguous_or_invalid_final'
    return parse_scalar(text)


def evaluate(run):
    original=json.loads((run/'einzelfaelle_v2.json').read_text(encoding='utf-8'))
    original={(r['task_id'],r['variant']):r for r in original}
    refs=json.loads((run/'referenzen.json').read_text(encoding='utf-8'))
    rows=[json.loads(s) for s in (run/'antworten.jsonl').read_text(encoding='utf-8').splitlines()]
    metadata=json.loads((run/'lauf.json').read_text(encoding='utf-8'))
    keys=[(r['task_id'],r['variant']) for r in rows]
    if len(keys)!=len(set(keys)) or set(keys)!=set(original) or len(keys)!=metadata['planned_requests']:
        raise ValueError('Antworten und ursprüngliche Einzelfallauswertung passen nicht zusammen.')
    if any(r['fingerprint']!=metadata['fingerprint'] for r in rows):
        raise ValueError('Antworten stammen aus unterschiedlichen Versuchsaufbauten.')
    counts={v:Counter() for v in ('zero_shot','few_shot','cot')}
    changes=[]
    details=[]
    for row in rows:
        value,method=extract(row['text'])
        target=Fraction(refs[row['task_id']])
        completed=row['response']['status']=='completed'
        exact=value is not None and value==target
        correct=completed and value is not None and abs(value-target)<=ABSOLUTE_TOLERANCE
        count=counts[row['variant']]
        count['answers']+=1
        count['correct']+=int(correct)
        count['unextractable']+=int(value is None)
        count['incomplete']+=int(not completed)
        count['correct_only_by_tolerance']+=int(correct and not exact)
        old=original[row['task_id'],row['variant']]
        count['original_format_compliant']+=int(old['format_compliant'])
        details.append({'task_id':row['task_id'],'variant':row['variant'],
            'completed':completed,'correct':correct,'extraction_method':method,
            'extracted':str(value) if value is not None else None,
            'reference':refs[row['task_id']],
            'original_format_compliant':old['format_compliant']})
        if correct!=old['correct']:
            changes.append({'task_id':row['task_id'],'variant':row['variant'],
                'previously_correct':old['correct'],'now_correct':correct,
                'method':method,'reference':refs[row['task_id']],
                'extracted':str(value) if value is not None else None,
                'response_excerpt':row['text'][:600]})
    summary={'evaluation_version':VERSION,'post_hoc':True,'absolute_tolerance':'1e-9','relative_tolerance':0,
             'source_run':run.name,'responses':len(rows),'changed':len(changes),'variants':{},
             'source_response_sha256':hashlib.sha256((run/'antworten.jsonl').read_bytes()).hexdigest(),
             'evaluator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    for variant,count in counts.items():
        summary['variants'][variant]={**dict(count),'accuracy':count['correct']/count['answers']}
    return summary,changes,details


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    summary,changes,details=evaluate(args.run)
    args.output.mkdir(parents=True,exist_ok=True)
    for name,value in [('auswertung_v3.json',summary),('geaenderte_bewertungen_v3.json',changes),('einzelfaelle_v3.json',details)]:
        (args.output/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))
