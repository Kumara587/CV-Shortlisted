"""Exercise the real disposable parser, including Linux resource limits."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
import pymupdf


class ParserWorkerTests(unittest.TestCase):
    def parse(self,data,name,mime):
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('parse_worker.py')),name,mime],
                              input=data,capture_output=True,timeout=12)
        self.assertEqual(result.returncode,0,'Parser worker exited unexpectedly')
        return json.loads(result.stdout)

    def test_pdf_text_under_worker_limits(self):
        with pymupdf.open() as document:
            page=document.new_page()
            page.insert_text((72,72),'Synthetic candidate: Python and SQL experience')
            data=document.tobytes()
        result=self.parse(data,'sample.pdf','application/pdf')
        self.assertEqual(result['status'],'parsed',result.get('error'))
        self.assertIn('Python and SQL',result['text'])

    def test_txt_and_malformed_pdf(self):
        self.assertEqual(self.parse(b'Synthetic candidate','sample.txt','text/plain')['status'],'parsed')
        result=self.parse(b'%PDF-invalid','broken.pdf','application/pdf')
        self.assertEqual(result['status'],'error')
        self.assertEqual(result['text'],'')


if __name__=='__main__':unittest.main()

