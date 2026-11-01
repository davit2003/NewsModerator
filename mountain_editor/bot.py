import copy
import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from .providers import post
from .moderation import Moderation

HELP = '''Команды:
/find — обновить подборку историй
/inbox — открыть сохранённую подборку
/budget — расход AI и месячный лимит
/health — состояние источников
/queue — последние черновики
/preview ID — актуальный предпросмотр
/edit ID новый текст — заменить текст целиком, включая источник
/rewrite ID пожелание — переписать с AI
/schedule ID VERSION 2026-12-01T18:00:00+01:00 — утвердить указанную версию на время
/context текст — заменить редакционные предпочтения и контекст Instagram/поездок
/pause и /resume — остановить/возобновить поиск и публикацию
Для обычной работы используйте кнопки меню и кнопки под постом.
/photos — добавить фото в коллекцию; /cancel — отменить действие.
Публикация требует актуального одобрения. Время поиска: Europe/Warsaw.
'''


class Bot(Moderation):
    def __init__(self, store, editor):
        self.store, self.editor = store, editor
        self.token = os.environ['TELEGRAM_BOT_TOKEN']
        self.owner = int(os.environ['OWNER_TELEGRAM_ID'])
        self.allowed_users = {self.owner} | {int(x.strip()) for x in os.getenv('ALLOWED_TELEGRAM_IDS','').split(',') if x.strip()}
        if any(x <= 0 for x in self.allowed_users):
            raise ValueError('Moderator IDs must be positive Telegram user IDs')
        self.target = os.environ['TARGET_CHAT_ID']
        self.live = os.getenv('PUBLISH_ENABLED','false').lower() == 'true'
        if self.live and editor.provider.name == 'demo':
            raise ValueError('Demo provider cannot publish. Select a real AI provider first.')

    def api(self, method, **payload):
        data = post('https://api.telegram.org/bot'+self.token+'/'+method,payload,timeout=120)
        if not data.get('ok'):
            raise ValueError('Telegram rejected the operation')
        return data['result']

    def tell(self, text):
        return self.api('sendMessage',chat_id=self.owner,text=text[:4000])

    def preview(self, id, photo_sent=False):
        row = self.store.get(id)
        if not row['photo'] and not row.get('text_only') and row['state'] == 'draft' and row['expires'] > time.time():
            photo_sent = self.web_photo(id)
            if not photo_sent:
                self.choose_photo(id)
            row = self.store.get(id)
        caption = row['text']+ ('\n\n'+row['credit'] if row['credit'] else '')
        if row['photo'] and not photo_sent:
            try:
                self.api('sendPhoto',chat_id=self.owner,photo=row['photo'],caption=caption)
            except ValueError as error:
                if 'wrong file identifier' not in str(error): raise
                # Telegram file IDs belong to the issuing bot, not the shared database.
                if row['state'] not in ('draft','approved'): raise
                self.store.edit(id,photo=None,credit=None)
                self.store.set(f'commons_seen:{id}','[]')
                if self.web_photo(id):
                    return self.preview(id,photo_sent=True)
                row=self.store.get(id)
                self.tell(row['text'])
                self.tell('Сохранённое фото недоступно этому боту. Выберите другое фото или «Без фото».')
        elif not row['photo']:
            self.tell(caption)
        version = row['version']
        buttons = {'inline_keyboard':[
            [{'text':'✅ Опубликовать','callback_data':f'publish:{id}:{version}'},
             {'text':'❌ Пропустить','callback_data':f'reject:{id}:{version}'}],
            [{'text':'✏️ Изменить текст','callback_data':f'edit:{id}:{version}'},
             {'text':'🖼 Изменить фото','callback_data':f'photo:{id}:{version}'}],
            [{'text':'🔄 Переписать','callback_data':f'rewrite:{id}:{version}'},
             {'text':'Без фото','callback_data':f'textonly:{id}:{version}'}]]}
        self.api('sendMessage',chat_id=self.owner,
                 text=f"Черновик {id} · версия {row['version']} · {row['state']}\n{row['reason'][:1200]}\n"
                      +('Можно добавить фото или выбрать «Без фото».\n' if not row['photo'] and not row.get('text_only') else '')+'Выберите действие ниже.\n'
                      +('ПУБЛИКАЦИЯ ОТКЛЮЧЕНА' if not self.live else ''),reply_markup=buttons)

    def show_inbox(self, offset=0, category='all'):
        from .inbox import CATEGORIES
        self.clear_dialog()
        rows = self.editor.inbox.rows(category)
        if offset >= len(rows): offset = 0
        self.tell(f'Подборка: {len(rows)} вариантов. Выберите историю — подготовлю короткий пост и иллюстрацию.')
        for row in rows[offset:offset+5]:
            self.api('sendMessage',chat_id=self.owner,
                text=f"{row['title']}\n\n{row['summary']}\n\n{CATEGORIES[row['category']]} · {row['url']}",
                reply_markup={'inline_keyboard':[[
                    {'text':'Подготовить пост','callback_data':f"idea:{row['id']}"},
                    {'text':'Пропустить','callback_data':f"skipidea:{row['id']}"}]]})
        self.api('sendMessage',chat_id=self.owner,text='Выберите действие:',reply_markup={'inline_keyboard':[
            [{'text':'Ещё варианты','callback_data':f'inbox:{offset+5}:{category}'},
             {'text':'Обновить','callback_data':'refreshinbox'}],
            [{'text':'Природа','callback_data':'inbox:0:nature'},
             {'text':'Полезное','callback_data':'inbox:0:education'},
             {'text':'Все','callback_data':'inbox:0:all'}]]})

    def find(self):
        if self.editor.provider.name == 'demo':
            id = self.editor.discover()
            if id: self.preview(id)
            return
        self.tell(self.editor.inbox.refresh())
        self.show_inbox()

    def process(self, update):
        callback = update.get('callback_query')
        event = callback or update.get('message',{})
        actor = event.get('from',{}).get('id')
        chat = (event.get('message',{}) if callback else event).get('chat',{}).get('id')
        if actor not in getattr(self,'allowed_users',{self.owner}) or chat != actor:
            return
        # Request-local identity; background notifications still go to the primary owner.
        session = copy.copy(self)
        session.owner = actor
        try:
            session._process_authorized(update)
        except ValueError as error:
            print('Command failed: '+str(error),flush=True)
            session.tell(str(error))
            error.moderator_notified = True
            raise

    def _process_authorized(self, update):
        callback = update.get('callback_query')
        message = update.get('message',{})
        if callback:
            # Both identity and private preview chat must match; forwarded controls are inert.
            if callback['from']['id'] != self.owner or callback.get('message',{}).get('chat',{}).get('id') != self.owner:
                return
            self.api('answerCallbackQuery',callback_query_id=callback['id'])
            data = callback.get('data','')
            if data == 'refreshinbox':
                self.find()
                return
            if data.startswith('inbox:'):
                _,offset,category = data.split(':')
                self.show_inbox(int(offset),category)
                return
            if data.startswith(('idea:','skipidea:')):
                action,id = data.split(':')
                if action == 'idea':
                    self.tell('Готовлю короткий пост и иллюстрацию…')
                    self.preview(self.editor.inbox.draft(int(id)))
                else:
                    self.editor.inbox.skip(int(id))
                    self.tell('Убрано из подборки.')
                return
            if self.moderation_callback(data):
                return
            action,id,version = callback['data'].split(':')
            id,version = int(id),int(version)
            if action == 'publish':
                self.valid_draft(id,version)
                if not self.live:
                    self.tell('Публикация отключена. Для запуска установите PUBLISH_ENABLED=true.')
                    return
                self.store.approve(id,version,self.owner,self.owner)
                self.clear_dialog()
                self.publish_due()
                state = self.store.get(id)['state']
                self.tell('Опубликовано ✅' if state == 'published' else 'Статус: '+state)
            elif action == 'reject':
                self.valid_draft(id,version)
                self.clear_dialog()
                self.store.reject(id,version)
                self.tell('Отклонено (если версия ещё актуальна).')
            return
        if message.get('from',{}).get('id') != self.owner or message.get('chat',{}).get('id') != self.owner:
            return
        text = message.get('text',message.get('caption','')).strip()
        if self.moderation_message(message,text):
            return
        command,_,args = text.partition(' ')
        command = command.split('@')[0]
        if command in ('/start','/help'):
            self.menu('Я найду историю и предложу фото с Wikimedia Commons. Вы решаете: опубликовать, изменить или пропустить.\nСвои фотографии можно добавить по желанию.')
            if command == '/help':
                self.tell(HELP)
        elif command == '/find':
            self.find()
        elif command == '/inbox':
            self.show_inbox()
        elif command == '/budget':
            from .budget import Budget
            self.tell(Budget(self.store).report())
        elif command == '/health':
            self.tell(self.store.setting('inbox_report','Сбор ещё не запускался.')+'\n'+self.store.setting('source_health',''))
        elif command == '/queue':
            self.queue()
        elif command == '/preview':
            self.preview(int(args))
        elif command in ('/edit','/rewrite','/photo'):
            id,_,content = args.partition(' ')
            id = int(id)
            if command == '/edit':
                self.store.edit(id,text=content)
            elif command == '/rewrite':
                self.editor.rewrite(id,content)
            else:
                if not message.get('photo') or not content.endswith('RIGHTS_OK'):
                    raise ValueError('Отправьте фото с подписью /photo ID Фото: автор. Иллюстрация. RIGHTS_OK')
                credit = content.removesuffix('RIGHTS_OK').strip()
                if not credit or len(credit.encode('utf-16-le'))//2 > 150:
                    raise ValueError('Укажите подпись к фото длиной до 150 символов')
                self.store.edit(id,photo=message['photo'][-1]['file_id'],credit=credit,text_only=0)
            self.preview(id)
        elif command == '/schedule':
            if not self.live:
                raise ValueError('Публикация отключена')
            id,version,when = args.split()
            due = datetime.fromisoformat(when)
            if due.tzinfo is None:
                raise ValueError('Укажите часовой пояс, например +01:00 или +02:00')
            self.store.approve(int(id),int(version),self.owner,self.owner,due.timestamp())
            self.tell('Утверждено и запланировано. Любое изменение отменит одобрение.')
        elif command == '/context':
            self.store.set('context',args[:12000])
            self.tell('Контекст обновлён.')
        elif command in ('/pause','/resume'):
            self.store.set('paused','1' if command == '/pause' else '0')
            self.tell('Приостановлено.' if command == '/pause' else 'Возобновлено.')
        else:
            self.tell(HELP)

    def publish_due(self):
        if not self.live or self.store.setting('paused') == '1':
            return
        rows = self.store.db.execute("SELECT id FROM drafts WHERE state='approved' AND due<=?", (time.time(),)).fetchall()
        for row in rows:
            id = row['id']
            if not self.store.claim(id):
                continue
            draft = self.store.get(id)
            try:
                if draft.get('text_only'):
                    result = self.api('sendMessage',chat_id=self.target,text=draft['text'],
                                      link_preview_options={'is_disabled':True})
                else:
                    result = self.api('sendPhoto',chat_id=self.target,photo=draft['photo'],
                                      caption=draft['text']+'\n\n'+draft['credit'])
                self.store.finish(id,result['message_id'])
            except Exception:
                self.store.finish(id)
                self.tell(f'Публикация {id}: результат не подтверждён. Проверьте группу вручную. Автоповтора не будет.')

    def scheduled_research(self):
        if self.store.setting('paused') == '1' or os.getenv('AUTO_RESEARCH','false').lower() != 'true':
            return
        # Four-hour collection; one broad web-search request per day inside Inbox.
        now = time.time()
        if now - float(self.store.setting('scheduled_inbox_attempt','0')) < 4*3600:
            return
        self.store.set('scheduled_inbox_attempt',now)
        report = self.editor.inbox.refresh()
        local = datetime.now(ZoneInfo('Europe/Warsaw'))
        day = local.date().isoformat()
        if local.hour >= 10 and self.store.setting('inbox_notice_day') != day:
            self.tell(report+'\nОткройте «📥 Подборка», чтобы выбрать историю.')
            self.store.set('inbox_notice_day',day)

    def run(self):
        provider = self.editor.provider
        print(f'Bot started: provider={provider.name}; publishing={self.live}; auto_research='+str(os.getenv('AUTO_RESEARCH','false').lower()=='true'),flush=True)
        if os.getenv('AI_DIAGNOSTIC_ON_START','false').lower() == 'true' and not self.store.setting('ai_diagnostic_v2'):
            self.store.set('ai_diagnostic_v2','started')
            try:
                provider.call('Find the official Tatra National Park Poland website. Return its URL.',search=True,max_tokens=128)
                self.store.set('ai_diagnostic_v2','AI connection succeeded')
                print('AI diagnostic: connection succeeded',flush=True)
            except ValueError as error:
                # APIError messages are constructed locally; no raw provider error bodies.
                self.store.set('ai_diagnostic_v2',str(error))
                print('AI diagnostic: '+str(error),flush=True)
            except Exception as error:
                self.store.set('ai_diagnostic_v2',type(error).__name__)
                print('AI diagnostic: '+type(error).__name__,flush=True)
        try:
            identity = self.api('getMe')
            print('Telegram identity: @'+str(identity.get('username','unknown')),flush=True)
            self.menu('Редактор запущен. '+('Публикация включена.' if self.live else 'Публикация отключена.'))
        except ValueError as error:
            print('Startup notification failed: '+str(error),flush=True)
            # A missing private chat must not prevent receiving /start.

        while True:
            try:
                updates = self.api('getUpdates',offset=int(self.store.setting('offset','0')),timeout=20,
                                   allowed_updates=['message','callback_query'])
                for update in updates:
                    # At-most-once command processing: do not replay side effects after a crash.
                    self.store.set('offset',update['update_id']+1)
                    try:
                        self.process(update)
                    except ValueError as error:
                        print('Command failed: '+str(error),flush=True)
                        if not getattr(error,'moderator_notified',False):
                            self.tell(str(error))
                    except Exception as error:
                        print('Command failed: '+type(error).__name__,flush=True)
                        self.tell('Ошибка внешнего сервиса. Проверьте /queue перед повтором команды.')
                self.publish_due()
                self.scheduled_research()
            except ValueError as error:
                print('Worker validation: '+str(error),flush=True)
                time.sleep(5)
            except Exception as error:
                # Error class only: exception strings can contain API keys.
                print('Worker error:',type(error).__name__,flush=True)
                time.sleep(5)

