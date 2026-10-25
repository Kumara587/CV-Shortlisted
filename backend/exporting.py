"""CSV cells are text escaped before RFC-style quoting."""
import csv
from io import StringIO
import unicodedata


def safe_cell(value):
    value='' if value is None else str(value)
    # Remove control characters, including tabs/CR/LF used to conceal prefixes.
    value=''.join(c for c in value if unicodedata.category(c) not in {'Cc','Cf'})
    probe=unicodedata.normalize('NFKC',value).lstrip()
    if probe.startswith(('=','+','-','@')):
        value="'"+value
    return value


def export_csv(rows,blind=False):
    stream=StringIO(newline='')
    writer=csv.writer(stream,quoting=csv.QUOTE_ALL,lineterminator='\r\n')
    writer.writerow(['Rank','Candidate','Evidence score','Review group','Human review','Supported skills','Missing or uncertain','Must-have review'])
    for index,row in enumerate(rows,1):
        writer.writerow([safe_cell(v) for v in [row['rank'],f'Candidate {index:02d}' if blind else row['label'],row['score'] if row['score'] is not None else 'Unscored',row['group'],row['review_status'],'; '.join(row['supported_skills']),'; '.join(row['missing_or_uncertain']),'; '.join(row['must_have_issues'])]])
    return ('\ufeff'+stream.getvalue()).encode('utf-8')
