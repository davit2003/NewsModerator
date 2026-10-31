import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from .providers import parse_json


def canonical(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username:
        raise ValueError('Only HTTPS sources are allowed')
    return urlunsplit((parts.scheme, parts.netloc.lower(),parts.path.rstrip('/'),parts.query,''))


class Editor:
    def __init__(self, store, provider):
        self.store, self.provider = store, provider
        self.brief = Path(__file__).resolve().parent.parent.joinpath('editorial.md').read_text()
        from .inbox import Inbox
        self.inbox = Inbox(store, provider, self.brief)

    def discover(self):
        if self.provider.name == 'demo':
            id = self.store.add('demo', 'ДЕМО — пример формата, не новость\n\n🏔 Что для вас идеальный день в горах: длинный маршрут или время посидеть с видом на вершины?\n\nПоделитесь — интересно, кто у нас в команде ранних стартов, а кто любит идти без спешки.', [], 'Проверка интерфейса без API и публикации.')
            if not id:
                id = next((r['id'] for r in self.store.recent() if r['story_key']=='demo' and r['state']=='draft'),None)
            if id:
                self.store.set(f'image_query:{id}','mountain landscape')
            return id
        self.inbox.refresh()
        rows = self.inbox.rows()
        return self.inbox.draft(rows[0]['id']) if rows else None

    def rewrite(self, id, instruction):
        row = self.store.get(id)
        if self.provider.name == 'demo':
            raise ValueError('Переписывание доступно после подключения AI')
        prompt = self.brief+'\nRewrite the Russian text using the owner feedback. Preserve all facts and the source URL exactly. Return plain text, max 850 UTF-16 units.\nTEXT:\n'+row['text']+'\nFEEDBACK:\n'+instruction
        text, _ = self.provider.call(prompt)
        for source in json.loads(row['sources']):
            if source in row['text'] and source not in text:
                raise ValueError('Переписанный текст потерял ссылку на источник')
        self.store.edit(id,text=text)

