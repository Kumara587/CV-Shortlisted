"""Gemini development adapter. Only explicitly confirmed synthetic data is allowed."""
import json
import os
import re
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError


def config_path():
    return Path(os.getenv('GEMINI_CONFIG_FILE', str(Path(os.getenv('LOCALAPPDATA', str(Path.home()/'.config')))/'CVShortlisted'/'secrets'/'gemini.credentials.json')))


def valid_key(value):
    # Credentials are opaque. Validate header safety, not a provider-specific prefix.
    return isinstance(value,str) and 20<=len(value)<=4096 and all(33<=ord(c)<=126 for c in value) and not any(c in value for c in '\"\'')


def provider_schema(schema):
    """Inline local Pydantic refs; enforce full constraints on the backend."""
    definitions=schema.get('$defs',{})
    allowed={'type','properties','required','items','enum','description','anyOf'}
    def expand(node):
        if isinstance(node,list):return [expand(v) for v in node]
        if not isinstance(node,dict):return node
        if '$ref' in node:
            ref=node['$ref']
            if not ref.startswith('#/$defs/'):raise ValueError('Unsupported schema reference')
            return expand(definitions[ref.split('/')[-1]])
        return {k:({name:expand(value) for name,value in v.items()} if k=='properties' else expand(v))
                for k,v in node.items() if k in allowed}
    return expand(schema)


def settings():
    try:
        value=json.loads(config_path().read_text(encoding='utf-8'))
        if value.get('provider')!='gemini' or value.get('synthetic_only') is not True:
            raise ValueError()
        if not valid_key(value.get('api_key','')):
            raise ValueError()
        if not re.fullmatch(r'gemini-[a-z0-9.-]+',value.get('model','')):
            raise ValueError()
        return value
    except (OSError,ValueError,TypeError,AttributeError):
        from llm_service import AIUnavailable
        raise AIUnavailable('Gemini is not configured. Run backend/setup_gemini.py and enter the API key privately.') from None


class GeminiClient:
    def __init__(self):
        from llm_service import NoRedirect
        self.config=settings()
        self.model=self.config['model']
        self.model_version=None
        self.opener=build_opener(ProxyHandler({}),NoRedirect())

    def versions(self,deadline):
        from llm_service import EXTRACTION_PROMPT_VERSION,EVALUATION_PROMPT_VERSION,SCORING_POLICY_VERSION
        # Updated after each response, before the service returns/saves this dict.
        if hasattr(self,'metadata'):return self.metadata
        self.metadata={'provider':'gemini','model':self.model,'model_digest':'provider-managed',
            'data_mode':'synthetic-only','extraction_prompt':EXTRACTION_PROMPT_VERSION,
            'evaluation_prompt':EVALUATION_PROMPT_VERSION,'scoring_policy':SCORING_POLICY_VERSION}
        return self.metadata

    def generate(self,schema,system,data,timeout):
        from llm_service import AIUnavailable,AIProviderError,MAX_RESPONSE
        body={'systemInstruction':{'parts':[{'text':system}]},
            'contents':[{'role':'user','parts':[{'text':json.dumps(data,ensure_ascii=False)}]}],
            'generationConfig':{'temperature':0,'maxOutputTokens':12000,
                'responseMimeType':'application/json','responseJsonSchema':provider_schema(schema)}}
        request=Request('https://generativelanguage.googleapis.com/v1beta/models/'+self.model+':generateContent',
            data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':self.config['api_key']},method='POST')
        try:
            with self.opener.open(request,timeout=timeout) as response:
                raw=response.read(MAX_RESPONSE+1)
            if len(raw)>MAX_RESPONSE: raise ValueError()
            result=json.loads(raw)
        except HTTPError as exc:
            # Never include provider response bodies: they can contain inputs or credentials.
            status=exc.code
            exc.close()
            message={400:'Gemini rejected the model/schema request. Check the configured model.',
                401:'Gemini API key is invalid.',403:'Gemini access denied. Check API key restrictions and region.',
                404:'Configured Gemini model is unavailable. Choose an available structured-output model.',
                429:'Gemini free-tier quota/rate limit reached. Wait and retry; check Google AI Studio quotas.'}.get(status,
                'Gemini service is unavailable. Retry later.')
            raise AIProviderError(message) from None
        except (URLError,TimeoutError,OSError):
            raise AIProviderError('Cannot reach Gemini or the request timed out. Check the backend internet connection.') from None
        except (ValueError,TypeError):
            raise AIUnavailable('Gemini returned an invalid or oversized response.') from None
        try:
            candidate=result['candidates'][0]
            if candidate.get('finishReason')!='STOP': raise ValueError()
            parts=candidate['content']['parts']
            output=''.join(p['text'] for p in parts if not p.get('thought') and isinstance(p.get('text'),str))
            parsed=json.loads(output)
            version=result.get('modelVersion')
            if isinstance(version,str) and len(version)<150:
                self.metadata['model_version']=version
            return parsed
        except (KeyError,IndexError,TypeError,ValueError):
            raise AIUnavailable('Gemini output was blocked, incomplete or invalid. No score was created.') from None
