import argparse
import json
import os
from .core import Store
from .providers import Provider
from .editor import Editor


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command',choices=['demo','run','check'])
    args = parser.parse_args()
    if args.command == 'demo':
        os.environ['AI_PROVIDER'] = 'demo'
        store = Store(':memory:')
        id = Editor(store,Provider(store)).discover()
        print(json.dumps(store.get(id),ensure_ascii=False,indent=2))
        return
    store = Store(os.getenv('DB_PATH','data/editor.db'))
    provider = Provider(store)
    required = ['TELEGRAM_BOT_TOKEN','OWNER_TELEGRAM_ID','TARGET_CHAT_ID']
    if provider.name != 'demo':
        required += ['OPENAI_API_KEY' if provider.name == 'openai' else 'GEMINI_API_KEY']
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        parser.error('Missing configuration: '+', '.join(missing))
    if args.command == 'check':
        print('Configuration present. No network calls made; credentials/model access not validated.')
        return
    from .bot import Bot
    Bot(store,Editor(store,provider)).run()


if __name__ == '__main__':
    main()
