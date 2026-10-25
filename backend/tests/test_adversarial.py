import struct
from io import BytesIO
import zipfile
import pytest
from parsing import parse_file,safe_name
from test_parsing import docx,DOC


def archive_with(entry):
    out=BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr(entry,b'target')
    return out.getvalue()

def test_symlink_entry():
    entry=zipfile.ZipInfo('word/link')
    entry.create_system=3
    entry.external_attr=0o120777<<16
    assert parse_file(archive_with(entry),'x.docx','')['error']['code']=='unsafe_archive'

def test_duplicate_members():
    out=BytesIO()
    with pytest.warns(UserWarning):
        with zipfile.ZipFile(out,'w') as z:
            z.writestr('same',b'a');z.writestr('same',b'b')
    assert parse_file(out.getvalue(),'x.docx','')['error']['code']=='unsafe_archive'

def test_encrypted_zip_bit():
    data=bytearray(docx())
    for signature,offset in [(b'PK\x03\x04',6),(b'PK\x01\x02',8)]:
        start=0
        while (at:=data.find(signature,start))!=-1:
            value=struct.unpack_from('<H',data,at+offset)[0]
            struct.pack_into('<H',data,at+offset,value|1)
            start=at+4
    assert parse_file(bytes(data),'x.docx','')['error']['code']=='encrypted'

def test_utf16_entities():
    content='<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE a [<!ENTITY x "boom">]><a>&x;</a>'.encode('utf-16')
    assert parse_file(docx(document=content),'x.docx','')['error']['code']=='unsafe_xml'

def test_unsupported_compression():
    assert parse_file(docx(compression=zipfile.ZIP_BZIP2),'x.docx','')['error']['code']=='unsafe_archive'

@pytest.mark.parametrize('name',['../../secret.pdf','C:\\users\\secret.pdf','\r\n=cmd.txt','CON.txt','file\x00.txt','..\\..\\outside.txt'])
def test_filename_cannot_be_a_path_or_header(name):
    cleaned=safe_name(name)
    assert not any(c in cleaned for c in ['/', '\\', '\r','\n','\x00'])
    assert not cleaned.startswith('.')

def test_long_numeric_and_whitespace_inputs_are_bounded():
    from main import CandidateInput,Requirements,extract
    from matching import rank_candidates
    # Regression: unbounded digit regex and adjacent whitespace quantifiers can backtrack.
    text='9'*200000
    assert extract(text).minimum_years is None
    req=Requirements(skills=[{'name':'Python     SQL'}],minimum_years=2)
    r=rank_candidates(req,[CandidateInput(id='a',text=text)])['results'][0]
    assert r['experience']['status']=='not_evidenced'
    r=rank_candidates(req,[CandidateInput(id='a',text='Python'+(' '*190000)+'missing')])['results'][0]
    assert r['skills'][0]['status']=='not_evidenced'

def test_repeated_evidence_is_bounded_but_conflicts_are_seen():
    from main import CandidateInput,Requirements
    from matching import rank_candidates
    r=rank_candidates(Requirements(skills=[{'name':'Python'}]),[CandidateInput(id='a',text=('Python\n'*1000)+'No Python experience')])['results'][0]
    assert len(r['skills'][0]['evidence'])<=3
    assert r['skills'][0]['status']=='uncertain'
