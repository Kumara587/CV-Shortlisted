"""Local bounded document parsing; no network calls or archive extraction."""
from io import BytesIO
from pathlib import PurePosixPath
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

MAX_BYTES = 5 * 1024 * 1024
MAX_TEXT = 200_000
MAX_EXPANDED = 20 * 1024 * 1024
MAX_MEMBER = 5 * 1024 * 1024
MAX_ENTRIES = 200
MAX_PAGES = 100
MIMES = {'pdf': {'application/pdf'}, 'docx': {'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}, 'txt': {'text/plain'}}

class ParseError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message

def safe_name(name):
    name = unicodedata.normalize('NFKC', name).replace('\\', '/').split('/')[-1]
    name = re.sub(r'[^\w. -]', '_', name).strip(' .')
    reserved = {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}
    if not name or name.split('.')[0].upper() in reserved:
        name = 'resume_' + name
    stem, dot, ext = name.rpartition('.')
    return (stem[:100] + dot + ext[:10]) if dot else name[:110]

def failure(name, ext, code, message):
    return {'filename': name, 'format': ext, 'status': 'error', 'text': '', 'warnings': [], 'error': {'code': code, 'message': message}}

def finish(text, warnings=None):
    text = text.replace('\x00', '').strip()
    if len(text) > MAX_TEXT:
        raise ParseError('text_limit', 'Extracted text exceeds 200,000 characters; split the document.')
    if not text:
        return {'status': 'needs_text', 'text': '', 'warnings': (warnings or []) + ['No readable text found. This may be scanned, image-only or blank. Paste text; OCR is not enabled.']}
    return {'status': 'parsed', 'text': text, 'warnings': warnings or []}

def xml(data):
    normalized = data.replace(b'\x00', b'').lower()
    if b'<!doctype' in normalized or b'<!entity' in normalized:
        raise ParseError('unsafe_xml', 'Document XML declarations are not supported.')
    return ET.fromstring(data)

def parse_docx(data):
    if data.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):
        raise ParseError('encrypted_or_legacy', 'Encrypted Office or legacy DOC detected. Save an unencrypted DOCX copy.')
    if not data.startswith(b'PK\x03\x04'):
        raise ParseError('type_mismatch', 'Content is not a DOCX ZIP package.')
    with zipfile.ZipFile(BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ENTRIES or sum(e.file_size for e in entries) > MAX_EXPANDED:
            raise ParseError('archive_limit', 'DOCX exceeds entry or expanded-size limits.')
        names = [e.filename for e in entries]
        if len(set(names)) != len(names):
            raise ParseError('unsafe_archive', 'Duplicate archive entries are not supported.')
        for e in entries:
            if '\\' in e.filename or e.filename.startswith('/') or '..' in PurePosixPath(e.filename).parts or ':' in e.filename or ((e.external_attr >> 16) & 0o170000) == 0o120000:
                raise ParseError('unsafe_archive', 'Unsafe archive member name or link.')
            if e.flag_bits & 1:
                raise ParseError('encrypted', 'Encrypted DOCX entries are not supported.')
            if e.file_size > MAX_MEMBER or e.file_size > max(1, e.compress_size) * 100:
                raise ParseError('archive_limit', 'DOCX member size or compression ratio exceeds limits.')
            if e.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise ParseError('unsafe_archive', 'Unsupported archive compression.')
        if not {'[Content_Types].xml', 'word/document.xml'}.issubset(names):
            raise ParseError('type_mismatch', 'ZIP file is not a Word DOCX document.')
        types = xml(archive.read('[Content_Types].xml'))
        ns = '{http://schemas.openxmlformats.org/package/2006/content-types}'
        if not any(e.get('PartName') == '/word/document.xml' and e.get('ContentType') == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml' for e in types.findall(ns+'Override')):
            raise ParseError('type_mismatch', 'Unsupported Word content type; macros are not accepted.')
        if any(n.lower().endswith('vbaproject.bin') for n in names):
            raise ParseError('unsafe_archive', 'Macro content is not accepted.')
        total = 0
        for e in entries:
            with archive.open(e) as source:
                count = 0
                while chunk := source.read(65536):
                    count += len(chunk)
                    total += len(chunk)
                    if count > MAX_MEMBER or total > MAX_EXPANDED:
                        raise ParseError('archive_limit', 'Actual archive expansion exceeds limits.')
        w = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        text = []
        for name in names:
            if name == 'word/document.xml' or re.fullmatch(r'word/(header|footer)\d+\.xml', name):
                root = xml(archive.read(name))
                if name == 'word/document.xml' and root.tag != w+'document':
                    raise ParseError('type_mismatch', 'Invalid Word document root.')
                for paragraph in root.iter(w+'p'):
                    text.append(''.join((node.text or '') if node.tag == w+'t' else '\t' if node.tag == w+'tab' else '\n' if node.tag in {w+'br',w+'cr'} else '' for node in paragraph.iter()))
        return finish('\n'.join(text), ['DOCX paragraphs, tables, headers and footers included; reading order may differ. Embedded files and external links are not opened.'])

def parse_file(data, filename, content_type):
    name = safe_name(filename)
    ext = name.rsplit('.',1)[-1].lower() if '.' in name else ''
    try:
        if ext not in MIMES:
            raise ParseError('unsupported_type', 'Use PDF, DOCX or TXT.')
        mime = content_type.split(';',1)[0].strip().lower()
        if mime not in MIMES[ext] | {'', 'application/octet-stream'}:
            raise ParseError('type_mismatch', 'Declared content type does not match the filename.')
        if len(data) > MAX_BYTES:
            raise ParseError('too_large', 'File exceeds 5 MB.')
        if not data:
            raise ParseError('empty_file', 'File is empty.')
        if ext == 'txt':
            if data.startswith((b'%PDF-',b'PK\x03\x04',bytes.fromhex('D0CF11E0A1B11AE1'))):
                raise ParseError('type_mismatch', 'Binary document renamed as TXT.')
            try:
                text = data.decode('utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
            except UnicodeError:
                raise ParseError('encoding', 'TXT must be UTF-8 or UTF-16 with a byte-order mark.')
            if any(ord(c)<32 and c not in '\t\n\r\f' for c in text):
                raise ParseError('binary_text', 'TXT contains binary control characters.')
            result = finish(text)
        elif ext == 'docx':
            result = parse_docx(data)
        else:
            if not data.startswith(b'%PDF-'):
                raise ParseError('type_mismatch', 'Content is not a PDF.')
            import pymupdf
            with pymupdf.open(stream=data, filetype='pdf') as document:
                if document.needs_pass:
                    raise ParseError('encrypted', 'Password-protected PDF. Save an unencrypted copy; passwords are not collected.')
                if len(document) > MAX_PAGES:
                    raise ParseError('page_limit', 'PDF exceeds 100 pages; split the document.')
                chunks, blank, length = [], 0, 0
                for page in document:
                    text = page.get_text('text', sort=True)
                    blank += not bool(text.strip())
                    chunks.append(text)
                    length += len(text)
                    if length > MAX_TEXT:
                        raise ParseError('text_limit', 'PDF text exceeds 200,000 characters.')
                result = finish('\n'.join(chunks), [f'{blank} page(s) have no text layer; they may be scanned or blank. No OCR was performed.'] if blank else [])
                result['pages'] = len(document)
        return {'filename': name, 'format': ext, **result, 'error': None}
    except ParseError as exc:
        return failure(name, ext, exc.code, exc.message)
    except Exception:
        return failure(name, ext, 'malformed', 'File could not be read. It may be corrupt, truncated or unsupported. Try a fresh export or paste text.')
