import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from gemini_provider import GeminiClient,valid_key,provider_schema
from llm_service import AIUnavailable,AIProviderError,require_data_confirmation,structured,job_source_quote,resolve_cv_evidence
from llm_contracts import Quote
from llm_contracts import Extraction
import time

CONFIG={'provider':'gemini','model':'gemini-2.5-flash','synthetic_only':True,'api_key':'fake-key-for-offline-tests-only'}

class GeminiTests(unittest.TestCase):
    def test_factory_uses_only_hosted_gemini(self):
        from llm_service import factory
        sentinel=object()
        with patch('gemini_provider.GeminiClient',return_value=sentinel),patch.dict(os.environ,{'LLM_PROVIDER':'ollama','LLM_MODEL':'unused'}):
            self.assertIs(factory(),sentinel)

    def test_invented_evidence_marks_review_without_credit(self):
        from types import SimpleNamespace
        from llm_contracts import Criterion,Evaluation
        from llm_service import ground_decisions,score_candidate
        candidate=SimpleNamespace(id='fake',text='Spreadsheet reporting.',parse_status='parsed',warnings=[])
        criteria=[Criterion(id='c1',text='HR certification',category='certification',importance='required',conditions=['HR certification'])]
        parsed=Evaluation.model_validate({'decisions':[{'criterion_id':'c1','conditions':[{'condition_index':0,'status':'meets','explanation':'Model claim','evidence':[{'quote':'Certified HR professional','line_start':1,'line_end':1}]}]}]})
        decisions=ground_decisions(parsed,criteria,candidate)
        self.assertEqual(decisions[0]['status'],'needs_review')
        self.assertEqual(decisions[0]['evidence'],[])
        result=score_candidate(candidate,decisions,{})
        self.assertEqual(result['score'],0)
        self.assertTrue(result['score_provisional'])
        self.assertEqual(result['group'],'must_have_review')
        self.assertTrue(result['warnings'])

    def test_reference_contract_never_requests_model_quotes(self):
        from llm_contracts import ReferencedEvaluation
        schema=provider_schema(ReferencedEvaluation.model_json_schema())
        self.assertNotIn('"quote"',json.dumps(schema))
        self.assertIn('line_start',json.dumps(schema))

    def test_source_references_and_scoring_are_job_independent(self):
        from types import SimpleNamespace
        from llm_contracts import Criterion,ReferencedEvaluation
        from llm_service import ground_references,score_candidate
        for requirement,text in [('HRIS','Maintained HRIS records.'),('Python','Built Python services.'),('Welding','Performed welding work.'),('Accounting','Prepared accounting reports.'),('Nursing','Provided nursing care.')]:
            with self.subTest(requirement=requirement):
                criteria=[Criterion(id='c1',text=requirement,importance='required',conditions=[requirement]),Criterion(id='c2',text='Additional certification',importance='preferred',conditions=['Additional certification'])]
                candidate=SimpleNamespace(id='fake',text=text,parse_status='parsed',warnings=[])
                parsed=ReferencedEvaluation.model_validate({'decisions':[{'criterion_id':'c1','conditions':[{'condition_index':0,'status':'meets','explanation':'Relevant source','evidence':[{'line_start':1,'line_end':1}]}]},{'criterion_id':'c2','conditions':[{'condition_index':0,'status':'meets','explanation':'Invalid source','evidence':[{'line_start':99,'line_end':99}]}]}]})
                decisions=ground_references(parsed,criteria,candidate)
                self.assertEqual(decisions[0]['evidence'][0]['quote'],text)
                self.assertEqual(decisions[1]['status'],'needs_review')
                score=score_candidate(candidate,decisions,{})
                self.assertEqual(score['score'],75)
                self.assertTrue(score['score_provisional'])

    def test_contact_lines_cannot_support_a_positive_decision(self):
        from types import SimpleNamespace
        from llm_contracts import Criterion,ReferencedEvaluation
        from llm_service import ground_references
        parsed=ReferencedEvaluation.model_validate({'decisions':[{'criterion_id':'c1','conditions':[{'condition_index':0,'status':'meets','explanation':'Invalid','evidence':[{'line_start':1,'line_end':1}]}]}]})
        rows=ground_references(parsed,[Criterion(id='c1',text='Communication',importance='required')],SimpleNamespace(text='Name: Fictional Person',id='fake'))
        self.assertEqual(rows[0]['status'],'needs_review')
        self.assertEqual(rows[0]['evidence'],[])
    def test_cv_line_references_are_derived_from_real_quotes(self):
        lines=['Sample CV','I use HRIS.','I manage records.']
        self.assertEqual(resolve_cv_evidence(Quote(quote='I use HRIS.',line_start=20,line_end=20),lines),(2,2,'I use HRIS.'))
        with self.assertRaisesRegex(ValueError,'Invented evidence'):
            resolve_cv_evidence(Quote(quote='I am HR certified.',line_start=2,line_end=2),lines)
        with self.assertRaisesRegex(ValueError,'Invalid source lines'):
            resolve_cv_evidence(Quote(quote='Repeated',line_start=20,line_end=20),['Repeated','Repeated'])
    def test_job_quotes_preserve_original_whitespace_and_reject_invention(self):
        source='Passed A/L AND  \r\nPassed O/L with credit passes'
        self.assertEqual(job_source_quote('Passed A/L AND\nPassed O/L',source),'Passed A/L AND  \r\nPassed O/L')
        for quote in ['Passed A/L OR Passed O/L','Passed A/L AND Passed O/L.','Passed A/L ... Passed O/L']:
            with self.assertRaises(ValueError):job_source_quote(quote,source)

    def test_schema_inlines_refs_without_losing_properties(self):
        schema=provider_schema(Extraction.model_json_schema())
        text=json.dumps(schema)
        self.assertNotIn('$ref',text)
        self.assertNotIn('$defs',text)
        self.assertIn('source_quote',schema['properties']['criteria']['items']['properties'])
        self.assertIn('source_quote',schema['properties']['criteria']['items']['required'])
    def test_opaque_key_header_safety(self):
        self.assertTrue(valid_key('AQ.'+'fictional_test_value_'*3))
        self.assertTrue(valid_key('fictional_'*40))
        for value in ['',None,'x'*19,'x'*4097,'x'*30+'\r\nHeader: value','"'+'x'*30+'"','x'*30+' space']:
            self.assertFalse(valid_key(value))

    def client(self):
        with patch('gemini_provider.settings',return_value=CONFIG):
            client=GeminiClient()
        client.versions(time.monotonic()+10)
        return client

    def test_request_and_version(self):
        client=self.client()
        response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"criteria":[]}'}]}}],'modelVersion':'gemini-test-version'}
        class Reply(io.BytesIO):pass
        with patch.object(client.opener,'open',return_value=Reply(json.dumps(response).encode())) as call:
            self.assertEqual(client.generate(Extraction.model_json_schema(),'system',{'job':'fake'},5),{'criteria':[]})
        req=call.call_args.args[0]
        self.assertNotIn(CONFIG['api_key'],req.full_url)
        self.assertEqual(req.get_header('X-goog-api-key'),CONFIG['api_key'])
        body=json.loads(req.data)
        self.assertIn('responseJsonSchema',body['generationConfig'])
        self.assertNotIn('tools',body)
        self.assertEqual(client.metadata['model_version'],'gemini-test-version')

    def test_quota_not_retried_or_echoed(self):
        client=self.client()
        with patch.object(client.opener,'open',side_effect=HTTPError('https://example.invalid',429,'secret body',{},None)) as call:
            with self.assertRaisesRegex(AIProviderError,'quota/rate limit'):
                structured(client,Extraction,'system',{},lambda v:v,time.monotonic()+10)
        self.assertEqual(call.call_count,1)

    def test_blocked_and_truncated(self):
        for response in [{},{'candidates':[{'finishReason':'MAX_TOKENS'}]}]:
            client=self.client()
            with patch.object(client.opener,'open',return_value=io.BytesIO(json.dumps(response).encode())):
                with self.assertRaises(AIUnavailable):client.generate({},'system',{},5)

    def test_cloud_requires_confirmation(self):
        with patch.dict(os.environ,{'LLM_PROVIDER':'gemini'}):
            with self.assertRaisesRegex(Exception,'fake/sample'):require_data_confirmation(False)
            require_data_confirmation(True)

if __name__=='__main__':unittest.main()
