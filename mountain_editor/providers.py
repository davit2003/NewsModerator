import json
import os
import urllib.request
from datetime import datetime, timezone


def post(url, payload, headers=None, timeout=100):
    req = urllib.request.Request(url, json.dumps(payload).encode(),
                                 {'Content-Type':'application/json', **(headers or {})})
    # Do not log request URLs: Telegram paths contain credentials.
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


class Provider:
    def __init__(self, store):
        self.store = store
        self.name = os.getenv('AI_PROVIDER', 'demo')
        self.model = os.getenv('AI_MODEL', '')
        if self.name not in ('demo','openai','gemini'):
            raise ValueError('AI_PROVIDER must be demo, openai or gemini')
        if self.name != 'demo' and not self.model:
            raise ValueError('Set AI_MODEL to an available model that supports web search')

    def call(self, prompt, search=False):
        if self.name == 'demo':
            raise ValueError('Demo does not call external AI')
        self.store.consume_call(datetime.now(timezone.utc).date().isoformat(), int(os.getenv('MAX_AI_CALLS_PER_DAY','12')))
        if self.name == 'openai':
            payload = {'model': self.model, 'input': prompt, 'max_output_tokens': 4500}
            if search:
                payload['tools'] = [{'type':'web_search'}]
                payload['include'] = ['web_search_call.action.sources']
            data = post('https://api.openai.com/v1/responses', payload,
                        {'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']})
            texts, sources = [], []
            for item in data.get('output',[]):
                for content in item.get('content',[]):
                    if content.get('type') == 'output_text':
                        texts.append(content['text'])
                        for annotation in content.get('annotations',[]):
                            if annotation.get('url'):
                                sources.append(annotation['url'])
                for source in item.get('action',{}).get('sources',[]):
                    if source.get('url'):
                        sources.append(source['url'])
            return '\n'.join(texts), list(dict.fromkeys(sources))
        payload = {'contents':[{'parts':[{'text':prompt}]}],
                   'generationConfig':{'maxOutputTokens':8192}}
        if search:
            payload['tools'] = [{'google_search':{}}]
        from urllib.parse import quote
        data = post('https://generativelanguage.googleapis.com/v1beta/models/'+quote(self.model,safe='')+':generateContent',
                    payload, {'x-goog-api-key':os.environ['GEMINI_API_KEY']})
        candidates = data.get('candidates',[])
        if not candidates:
            raise ValueError('Gemini returned no candidate')
        candidate = candidates[0]
        text = '\n'.join(p.get('text','') for p in candidate.get('content',{}).get('parts',[]) if not p.get('thought'))
        sources = [c['web']['uri'] for c in candidate.get('groundingMetadata',{}).get('groundingChunks',[]) if 'web' in c]
        return text, list(dict.fromkeys(sources))


def parse_json(text):
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n',1)[1].rsplit('```',1)[0]
    return json.loads(text)
