"""Button-based moderation and persistent, owner-scoped upload conversations."""
import json
import re
import time
import uuid


MENU = {
    'keyboard': [[{'text':'🔎 Найти материал'}, {'text':'📋 Черновики'}],
                 [{'text':'🖼 Мои фотографии'}, {'text':'↩️ Отмена'}]],
    'resize_keyboard': True,
}


class Moderation:
    def menu(self, text='Найдём интересную историю? Выберите действие ниже.'):
        self.api('sendMessage',chat_id=self.owner,text=text,reply_markup=MENU)

    def dialog(self):
        state = json.loads(self.store.setting('dialog','{}'))
        if state and (state.get('owner') != self.owner or state.get('expires',0) < time.time()):
            self.store.set('dialog','{}')
            return {}
        return state

    def set_dialog(self, mode, **values):
        state = dict(mode=mode,owner=self.owner,expires=time.time()+3600,token=uuid.uuid4().hex[:12],**values)
        self.store.set('dialog',json.dumps(state,ensure_ascii=False))
        return state

    def clear_dialog(self):
        self.store.set('dialog','{}')

    def valid_draft(self, id, version):
        row = self.store.get(id)
        if row['version'] != version or row['state'] not in ('draft','approved') or row['expires'] <= time.time():
            raise ValueError('Этот предпросмотр устарел. Откройте «📋 Черновики» и выберите актуальный.')
        return row

    def queue(self):
        self.clear_dialog()
        rows = self.store.recent()
        active = [r for r in rows if r['state'] in ('draft','approved') and r['expires']>time.time()]
        if not active:
            self.menu('Нет активных черновиков. Нажмите «🔎 Найти материал».')
            return
        self.api('sendMessage',chat_id=self.owner,text='Выберите черновик:',reply_markup={
            'inline_keyboard':[[{'text':r['text'][:60], 'callback_data':f"preview:{r['id']}:{r['version']}"}] for r in active]})

    def photo_setup(self, draft=None):
        values = {} if draft is None else {'draft':draft['id'],'version':draft['version']}
        state = self.set_dialog('rights',**values)
        self.api('sendMessage',chat_id=self.owner,
            text='Добавьте свои фотографии — я сохраню их и буду предлагать к постам как иллюстрации. '
                 'Вы подтверждаете, что можете использовать загружаемые фото в публикациях вашей компании? '
                 'Подтверждение действует для этой загрузки в течение часа.',
            reply_markup={'inline_keyboard':[[{'text':'Да, могу использовать','callback_data':'rights:'+state['token']},
                                              {'text':'Отмена','callback_data':'cancel:'+state['token']}]]})

    def choose_photo(self, id, exclude_current=False):
        row = self.store.get(id)
        candidates = [p for p in self.store.photos() if not exclude_current or p['file_id'] != row['photo']]
        if not candidates:
            return False
        # Caption matching only, not visual recognition. All library images are labeled illustrative.
        words = set(re.findall(r'\w{4,}',row['text'].lower()))
        candidates.sort(key=lambda p:(-len(words & set(re.findall(r'\w{4,}',p['description'].lower()))),p['last_used'],p['id']))
        self.store.use_photo(id,candidates[0])
        return True

    def moderation_callback(self, data):
        if data.startswith(('rights:','cancel:','done:')):
            action,token = data.split(':')
            state = self.dialog()
            if not state or token != state['token']:
                raise ValueError('Эта кнопка устарела. Откройте «🖼 Мои фотографии» снова.')
            if action == 'rights':
                if state['mode'] != 'rights':
                    raise ValueError('Загрузка уже началась.')
                state['mode'] = 'upload'
                self.store.set('dialog',json.dumps(state))
                self.api('sendMessage',chat_id=self.owner,
                    text='Отправьте фото обычным сообщением — без команд. Можно отправить альбом. '
                         'Необязательная подпись поможет подбору: место, сезон, что на фото. '
                         'После загрузки нажмите «Готово».',
                    reply_markup={'inline_keyboard':[[{'text':'Готово','callback_data':'done:'+token}]]})
            elif action == 'done':
                draft_id = state.get('draft')
                self.clear_dialog()
                if draft_id:
                    self.preview(draft_id)
                self.menu('Фотографии сохранены. Новые материалы будут приходить с фото из коллекции.')
            else:
                self.clear_dialog()
                self.menu('Действие отменено.')
            return True
        action,_,rest = data.partition(':')
        if action not in ('preview','edit','rewrite','photo','another','upload'):
            return False
        id,version = map(int,rest.split(':'))
        row = self.valid_draft(id,version)
        if action == 'preview':
            self.clear_dialog()
            self.preview(id)
        elif action in ('edit','rewrite'):
            self.set_dialog(action,draft=id,version=version)
            self.menu('Пришлите новый текст обычным сообщением. Ссылка на источник сохранится.' if action=='edit'
                      else 'Что изменить? Например: «Короче и с более конкретным началом».')
        elif action == 'photo':
            self.clear_dialog()
            self.api('sendMessage',chat_id=self.owner,text='Как заменить фото?',reply_markup={
                'inline_keyboard':[[{'text':'🔄 Другое из коллекции','callback_data':f'another:{id}:{version}'}],
                                   [{'text':'📷 Загрузить фото','callback_data':f'upload:{id}:{version}'}]]})
        elif action == 'another':
            self.clear_dialog()
            if self.choose_photo(id,exclude_current=True):
                self.preview(id)
            else:
                self.photo_setup(row)
        elif action == 'upload':
            self.photo_setup(row)
        return True

    def moderation_message(self, message, text):
        if text in ('↩️ Отмена','/cancel'):
            self.clear_dialog()
            self.menu('Действие отменено.')
            return True
        if text == '🔎 Найти материал':
            self.clear_dialog()
            self.tell('Ищу материал. Это может занять пару минут…')
            self.find()
            return True
        if text == '📋 Черновики':
            self.queue()
            return True
        if text in ('🖼 Мои фотографии','/photos'):
            self.photo_setup()
            return True
        # Slash commands continue through the compatibility handler.
        if text.startswith('/'):
            self.clear_dialog()
            return False
        state = self.dialog()
        if message.get('photo'):
            if state.get('mode') != 'upload':
                self.menu('Сначала нажмите «🖼 Мои фотографии», либо «Изменить фото» под нужным постом.')
                return True
            if state.get('draft'):
                self.valid_draft(state['draft'],state['version'])
            photo = message['photo'][-1]
            credit = 'Фото из коллекции организатора. Иллюстрация.'
            self.store.add_photo(photo['file_unique_id'],photo['file_id'],text,credit,self.owner)
            if state.get('draft') and not state.get('attached'):
                self.store.edit(state['draft'],photo=photo['file_id'],credit=credit)
                state['attached'] = True
                state['version'] = self.store.get(state['draft'])['version']
                self.store.set('dialog',json.dumps(state))
            self.api('sendMessage',chat_id=self.owner,text='Фото добавлено. Можно прислать ещё или закончить загрузку.',
                     reply_markup={'inline_keyboard':[[{'text':'Готово','callback_data':'done:'+state['token']}]]})
            return True
        if state.get('mode') in ('edit','rewrite') and text:
            row = self.valid_draft(state['draft'],state['version'])
            if state['mode'] == 'edit':
                for source in json.loads(row['sources']):
                    if source in row['text'] and source not in text:
                        text += '\n\nИсточник: '+source
                self.store.edit(row['id'],text=text)
            else:
                self.editor.rewrite(row['id'],text)
            self.clear_dialog()
            self.preview(row['id'])
            return True
        if state:
            self.menu('Жду фото или нажатия кнопки выше. Чтобы выйти, нажмите «↩️ Отмена».')
            return True
        return False
