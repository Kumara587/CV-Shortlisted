"""Diagnose only the public demonstration JD fixture, never applicant data."""
from pathlib import Path
import time
from gemini_provider import GeminiClient
from llm_contracts import Extraction,prohibited_criterion
from llm_service import EXTRACT_SYSTEM,locate_quote

text=Path(__file__).with_name('hr_demo_jd.txt').read_text(encoding='utf-8')
client=GeminiClient()
client.versions(time.monotonic()+90)
raw=client.generate(Extraction.model_json_schema(),EXTRACT_SYSTEM,{'job_description':text},45)
try:
    parsed=Extraction.model_validate(raw)
except Exception as exc:
    print('Schema validation:',type(exc).__name__)
    raise SystemExit(1)
print('Criteria:',len(parsed.criteria))
for c in parsed.criteria:
    try:locate_quote(c.source_quote,text);grounded=True
    except ValueError:grounded=False
    print(c.category,c.importance,'grounded:',grounded,'prohibited:',prohibited_criterion(c),c.text)
    if not grounded: print('Fixture quote:',repr(c.source_quote))
