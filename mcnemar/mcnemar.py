"""Nachträgliche McNemar-Auswertung (exakt, zweiseitig) auf den vorhandenen Einzelergebnissen.
Aufruf im Projektordner: python mcnemar/mcnemar.py   (benötigt scipy). Keine API-Aufrufe."""
import json
from pathlib import Path
from scipy.stats import binomtest

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
HAUPT = ROOT / "pilot/ergebnisse/hauptversuch_v1/einzelfaelle_v3.json"
ZUSATZ = ROOT / "zusatzstudie/ergebnisse/studie/einzelfaelle.json"

def mcnemar(a, b, ids):
    """a, b: dict id -> bool. Rückgabe: nur a richtig, nur b richtig, exakter p-Wert."""
    n_a = sum(1 for i in ids if a[i] and not b[i])
    n_b = sum(1 for i in ids if b[i] and not a[i])
    n = n_a + n_b
    p = binomtest(min(n_a, n_b), n, 0.5).pvalue if n else 1.0
    return {"nur_erste": n_a, "nur_zweite": n_b, "p_exakt_zweiseitig": p}

ergebnis = {}
h = {}
for r in json.load(open(HAUPT, encoding="utf-8")):
    h.setdefault(r["variant"], {})[r["task_id"]] = bool(r["correct"])
ids = sorted(h["zero_shot"])
for a, b in [("zero_shot", "few_shot"), ("zero_shot", "cot"), ("few_shot", "cot")]:
    ergebnis[f"hauptversuch: {a} gegen {b}"] = {"n": len(ids), **mcnemar(h[a], h[b], ids)}

z = {}
for r in json.load(open(ZUSATZ, encoding="utf-8")):
    task, cond = r["key"].split(":", 1)
    z.setdefault(cond, {})[task] = bool(r["correct"])
ids = sorted(z["luna_none:zero_shot"])
paare = []
for m in ["luna_none", "luna_low", "sol_low"]:
    paare += [(f"{m}:zero_shot", f"{m}:few_shot"), (f"{m}:zero_shot", f"{m}:cot"), (f"{m}:few_shot", f"{m}:cot")]
for v in ["zero_shot", "few_shot", "cot"]:
    paare += [(f"luna_none:{v}", f"luna_low:{v}"), (f"luna_low:{v}", f"sol_low:{v}")]
for a, b in paare:
    ergebnis[f"zusatzstudie: {a} gegen {b}"] = {"n": len(ids), **mcnemar(z[a], z[b], ids)}

json.dump(ergebnis, open(SCRIPT_DIR / "mcnemar_ergebnisse.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for k, v in ergebnis.items():
    print(f"{k}: {v['nur_erste']} zu {v['nur_zweite']}, p = {v['p_exakt_zweiseitig']:.4g}")
