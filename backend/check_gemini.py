"""Synthetic connectivity diagnostic; never prints the configured API key."""
import json
import argparse
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError,URLError
from gemini_provider import settings
from llm_service import NoRedirect

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model')
    parser.add_argument('--extraction-schema',action='store_true')
    args=parser.parse_args()
    config=settings()
    model=args.model or config['model']
    import re
    if not re.fullmatch(r'gemini-[a-z0-9.-]+',model):parser.error('Invalid model name')
    body={'contents':[{'parts':[{'text':'Fictional connectivity test. Return JSON with ok true.'}]}],
        'generationConfig':{'maxOutputTokens':256,'responseMimeType':'application/json',
            'responseJsonSchema':{'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok']}}}
    if args.extraction_schema:
        from llm_contracts import Extraction
        from gemini_provider import provider_schema
        body['generationConfig']['responseJsonSchema']=provider_schema(Extraction.model_json_schema())
    request=Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',
        data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':config['api_key']})
    try:
        with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=25) as response:
            result=json.load(response)
        print('Model:',model,'HTTP: 200')
        candidate=result.get('candidates',[{}])[0]
        print('Finish:',candidate.get('finishReason'))
        print('JSON received:',any('text' in p for p in candidate.get('content',{}).get('parts',[])))
    except HTTPError as exc:
        try:error=json.loads(exc.read(16384)).get('error',{})
        except (ValueError,TypeError):error={}
        message=str(error.get('message','')).replace(config['api_key'],'[redacted]')
        print('Model:',model,'HTTP:',exc.code,'Status:',error.get('status'))
        # This diagnostic sends only the fixed fictional prompt above, never applicant inputs.
        print(message[:700])
    except (URLError,OSError,TimeoutError):
        print('Model:',model,'Network request failed or timed out.')

if __name__=='__main__':main()
