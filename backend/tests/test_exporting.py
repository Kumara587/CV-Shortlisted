import csv
from io import StringIO
import pytest
from exporting import safe_cell,export_csv

@pytest.mark.parametrize('value',['=1+1',' +SUM(A1:A2)','-1+2','@SUM(A1)','\t=HYPERLINK("https://evil")','\r\n=cmd','\ufeff=1','\u200b=1','＝1','＋1','＠1'])
def test_dangerous_prefix(value):
    assert safe_cell(value).startswith("'")

def test_roundtrip_quotes_commas_unicode():
    row={'id':'a','rank':1,'label':'Ada, "Example" 日本','score':90,'group':'requirements_review','review_status':'pending','supported_skills':['=cmd'],'missing_or_uncertain':[],'must_have_issues':[]}
    data=export_csv([row]);rows=list(csv.reader(StringIO(data.decode('utf-8-sig'))))
    assert rows[1][1]==row['label'] and rows[1][5]=="'=cmd"
    assert 'Ada' not in export_csv([row],blind=True).decode()
