from io import BytesIO
import json
import subprocess
import sys
import zipfile
import pytest
import pymupdf
from parsing import parse_file, safe_name, MAX_BYTES

TYPES = b'''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'''
DOC = b'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Ada Python</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>SQL table</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'''

def docx(extra=None, document=DOC, compression=zipfile.ZIP_STORED):
    output = BytesIO()
    with zipfile.ZipFile(output, 'w', compression=compression) as z:
        z.writestr('[Content_Types].xml', TYPES)
        z.writestr('word/document.xml', document)
        for name, value in (extra or {}).items():
            z.writestr(name, value)
    return output.getvalue()

def pdf(text=True, encrypted=False, pages=1):
    with pymupdf.open() as d:
        for _ in range(pages):
            page = d.new_page()
            if text:
                page.insert_text((50,50), 'Ada Python developer')
        return d.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='secret') if encrypted else d.tobytes()

def test_formats():
    for data, name, expected in [(b'Ada Python','a.txt','Ada Python'), ('Ada Unicode'.encode('utf-16'),'a.txt','Ada Unicode'),(pdf(),'a.pdf','Ada Python'),(docx(),'a.docx','SQL table')]:
        result = parse_file(data, name, 'application/octet-stream')
        assert result['status'] == 'parsed', result
        assert expected in result['text']

def test_pdf_notices():
    assert parse_file(pdf(encrypted=True),'a.pdf','')['error']['code'] == 'encrypted'
    r = parse_file(pdf(text=False), 'scan.pdf', '')
    assert r['status'] == 'needs_text' and 'OCR' in ' '.join(r['warnings'])
    assert parse_file(pdf(pages=101),'a.pdf','')['error']['code'] == 'page_limit'

@pytest.mark.parametrize('data,name,mime,code', [
    (b'', 'a.txt','', 'empty_file'),
    (b'x'*(MAX_BYTES+1), 'a.txt','', 'too_large'),
    (b'hello','a.exe','', 'unsupported_type'),
    (b'hello','a.txt','application/pdf','type_mismatch'),
    (b'hello','a.pdf','', 'type_mismatch'),
    (b'%PDF-1.7 broken','a.pdf','', 'malformed'),
    (b'PK\x03\x04broken','a.docx','', 'malformed'),
    (b'%PDF-1.7','a.txt','', 'type_mismatch'),
    (b'\x00binary','a.txt','', 'binary_text'),
    (b'\xff\xff','a.txt','', 'encoding'),
    (bytes.fromhex('D0CF11E0A1B11AE1'),'a.docx','', 'encrypted_or_legacy'),
    (b'x'*200001,'a.txt','', 'text_limit'),
], ids=[f'case-{i}' for i in range(12)])
def test_rejected(data,name,mime,code):
    r = parse_file(data,name,mime)
    assert r['status'] == 'error' and r['text'] == ''
    assert r['error']['code'] == code

@pytest.mark.parametrize('data,code', [
    (docx({'../escape.txt':b'x'}),'unsafe_archive'),
    (docx({'word/media/bomb':b'x'*30000},compression=zipfile.ZIP_DEFLATED),'archive_limit'),
    (docx({f'e{i}':b'x' for i in range(201)}),'archive_limit'),
    (docx({'large':b'x'*(5*1024*1024+1)}),'too_large'),
    (docx(document=b'<!DOCTYPE a [<!ENTITY x "boom">]><a>&x;</a>'),'unsafe_xml'),
    (docx(document=b'<broken>'),'malformed'),
    (docx({'word/vbaProject.bin':b'x'}),'unsafe_archive'),
], ids=[f'archive-{i}' for i in range(7)])
def test_docx_attacks(data,code):
    assert parse_file(data,'a.docx','')['error']['code'] == code

def test_names():
    assert safe_name('../../Ada.txt') == 'Ada.txt'
    assert safe_name('C:\\private\\Ada.txt') == 'Ada.txt'
    assert safe_name('CON.txt') == 'resume_CON.txt'
    assert '/' not in safe_name('/x/evil\x00.txt')

def test_worker_memory_input():
    p = subprocess.run([sys.executable, 'parse_worker.py', 'resume.txt', 'text/plain'], input=b'Private resume Python', capture_output=True, timeout=15)
    assert p.returncode == 0
    assert json.loads(p.stdout)['text'] == 'Private resume Python'

def test_scanned_and_mixed_pdf():
    with pymupdf.open() as d:
        page = d.new_page()
        page.insert_image(pymupdf.Rect(10,10,100,100), stream=b'P6\n1 1\n255\n\xff\x00\x00')
        scanned = d.tobytes()
        d.new_page().insert_text((50,50),'Readable second page')
        mixed = d.tobytes()
    assert parse_file(scanned,'scan.pdf','')['status'] == 'needs_text'
    result = parse_file(mixed,'mixed.pdf','')
    assert result['status'] == 'parsed' and result['pages'] == 2
    assert '1 page' in result['warnings'][0]

def test_docx_headers_and_footer():
    header = b'<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Header name</w:t></w:r></w:p></w:hdr>'
    result = parse_file(docx({'word/header1.xml':header}), 'a.docx','')
    assert 'Header name' in result['text']

def test_total_expansion():
    data = docx({f'word/media/{i}': b'x'*(4*1024*1024) for i in range(5)},compression=zipfile.ZIP_DEFLATED)
    assert parse_file(data,'a.docx','')['error']['code'] == 'archive_limit'

def test_plain_zip_and_crc_error():
    out=BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('random.txt','hello')
    assert parse_file(out.getvalue(),'a.docx','')['error']['code'] == 'type_mismatch'
    damaged=docx().replace(b'Ada Python',b'Bad Python',1)
    assert parse_file(damaged,'a.docx','')['error']['code'] == 'malformed'
