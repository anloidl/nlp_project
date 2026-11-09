"""Operational fix: retry Windows file locks, without changing frozen study logic."""
import time
import re
from fractions import Fraction
import studie

original_write = studie.write

def retry_write(path, value):
    for attempt in range(120):
        try:
            return original_write(path, value)
        except PermissionError:
            if attempt == 119:
                raise
            time.sleep(0.5)

studie.write = retry_write

original_prepare = studie.prepare

def prepare_with_reference_numbers(phase):
    out, requests, references, config = original_prepare(phase)
    normalized = {}
    for key, value in references.items():
        # GSM8K uses English thousands grouping; keep saved source references intact.
        if ',' in value:
            if not re.fullmatch(r'[+-]?[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?', value):
                raise ValueError(f'Unexpected reference format at index {key}')
            value = value.replace(',', '')
        Fraction(value)  # Validate every selected reference before further API calls.
        normalized[key] = value
    return out, requests, normalized, config

studie.prepare = prepare_with_reference_numbers
if __name__ == '__main__':
    studie.main()
