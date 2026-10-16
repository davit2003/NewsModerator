import json
import os
import urllib.request
import urllib.error
import re
from urllib.parse import urlsplit
from datetime import datetime, timezone


class APIError(ValueError):
    """Safe structured error: never retain URLs, API keys or raw provider messages."""
    def __init__(self, service, status, code='unknown'):
        self.service, self.status = service, status
        allowed = {'insufficient_quota','invalid_api_key','model_not_found','rate_limit_exceeded',
                   'billing_hard_limit_reached','permission_denied','invalid_request_error',
                   'unsupported_parameter','unsupported_value','context_length_exceeded',
                   'RESOURCE_EXHAUSTED','UNAUTHENTICATED','PERMISSION_DENIED','INVALID_ARGUMENT'}
        self.code = code if code in allowed else 'unknown'
        if self.code in ('insufficient_quota','billing_hard_limit_reached'):
            hint = 'Недостаточно API-кредитов или достигнут лимит оплаты. Проверьте Billing в OpenAI API; подписка ChatGPT не оплачивает API.'
        elif status == 401:
            hint = 'Ключ API не принят. Проверьте ключ и проект в настройках сервиса.'
        elif self.code == 'model_not_found' or status == 404:
            hint = 'Модель не найдена или недоступна этому API-проекту. Проверьте AI_MODEL.'
        elif status == 403:
            hint = 'Нет доступа. Проверьте разрешения ключа и доступ проекта к модели.'
        elif status == 429:
            hint = 'Превышена квота или частота запросов. Проверьте Billing и Limits API-проекта.'
        elif status == 400:
            hint = 'API отклонил параметры запроса. Требуется проверить совместимость модели и web search.'
        else:
            hint = 'Внешний сервис временно недоступен. Повторите позже.'
        super().__init__(f'{service}: HTTP {status}, {self.code}. {hint}')


def post(url, payload, headers=None, timeout=100):
    req = urllib.request.Request(url, json.dumps(payload).encode(),
                                 {'Content-Type':'application/json', **(headers or {})})
    # Do not log request URLs: Telegram paths contain credentials.
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        host = urlsplit(url).hostname
        service = {'api.openai.com':'OpenAI','api.telegram.org':'Telegram',
                   'generativelanguage.googleapis.com':'Gemini'}.get(host,'API')
        code = 'unknown'
        try:
            body = json.loads(error.read(65536))
            details = body.get('error',{})
            if isinstance(details,dict):
                code = details.get('code') or details.get('status') or details.get('type') or 'unknown'
        except (ValueError,AttributeError):
            pass
        raise APIError(service,error.code,code) from None
    except (urllib.error.URLError,TimeoutError):
        raise ValueError('Сетевая ошибка или тайм-аут внешнего API. Попробуйте позже.') from None


class Provider:
    def __init__(self, store):
        self.store = store
        self.name = os.getenv('AI_PROVIDER', 'demo').strip().lower()
        self.model = os.getenv('AI_MODEL', '').strip()
        if self.name not in ('demo','openai','gemini'):
            raise ValueError('AI_PROVIDER must be demo, openai or gemini')
        if self.name != 'demo' and not self.model:
            raise ValueError('Set AI_MODEL to an available model that supports web search')

    def call(self, prompt, search=False, max_tokens=4500):
        if self.name == 'demo':
            raise ValueError('Demo does not call external AI')
        self.store.consume_call(datetime.now(timezone.utc).date().isoformat(), int(os.getenv('MAX_AI_CALLS_PER_DAY','12')))
        safe_model = self.model if re.fullmatch(r'[a-zA-Z0-9._-]{1,80}',self.model) and not self.model.startswith('sk-') else '[invalid model setting]'
        print(f'AI request: provider={self.name} model={safe_model} search={search}',flush=True)
        if self.name == 'openai':
            payload = {'model': self.model, 'input': prompt, 'max_output_tokens': max_tokens}
            if search:
                payload['tools'] = [{'type':'web_search'}]
                payload['include'] = ['web_search_call.action.sources']
            data = post('https://api.openai.com/v1/responses', payload,
                        {'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'].strip()})
            print('AI response: provider=openai status='+str(data.get('status','unknown')),flush=True)
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
                   'generationConfig':{'maxOutputTokens':max_tokens if max_tokens!=4500 else 8192}}
        if search:
            payload['tools'] = [{'google_search':{}}]
        from urllib.parse import quote
        data = post('https://generativelanguage.googleapis.com/v1beta/models/'+quote(self.model,safe='')+':generateContent',
                    payload, {'x-goog-api-key':os.environ['GEMINI_API_KEY'].strip()})
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
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ValueError('AI вернул некорректный формат черновика. Попробуйте ещё раз.') from None

