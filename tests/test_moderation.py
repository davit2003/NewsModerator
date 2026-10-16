import json
import tempfile
import unittest
from unittest.mock import Mock
from mountain_editor.core import Store
from mountain_editor.bot import Bot


class ModerationTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(':memory:')
        self.bot = Bot.__new__(Bot)
        self.bot.store = self.store
        self.bot.owner = 1
        self.bot.live = False
        self.bot.api = Mock(return_value={'message_id':10})
        self.bot.editor = Mock()
        self.id = self.store.add('story','Татры осенью\nИсточник: https://example.org', ['https://example.org'],'Relevant')

    def message(self, text='', photo=False, user=1, chat=1):
        msg = {'from':{'id':user},'chat':{'id':chat}}
        msg['caption' if photo else 'text'] = text
        if photo:
            msg['photo'] = [{'file_id':'file-a','file_unique_id':'unique-a'}]
        self.bot.process({'message':msg})

    def callback(self, data, user=1, chat=1):
        self.bot.process({'callback_query':{'id':'callback','from':{'id':user},
                                          'message':{'chat':{'id':chat}},'data':data}})

    def upload_setup(self, draft=False):
        if draft:
            self.callback(f'upload:{self.id}:1')
        else:
            self.message('🖼 Мои фотографии')
        self.callback('rights:'+self.bot.dialog()['token'])

    def test_upload_without_commands(self):
        self.upload_setup()
        self.message('Татры осенью',photo=True)
        self.assertEqual(len(self.store.photos()),1)
        self.assertEqual(self.store.photos()[0]['confirmed_by'],1)
        self.assertTrue(self.bot.choose_photo(self.id))
        self.assertEqual(self.store.get(self.id)['photo'],'file-a')

    def test_unconfirmed_upload_not_saved(self):
        self.message(photo=True)
        self.assertEqual(self.store.photos(),[])

    def test_old_consent_button_rejected(self):
        self.message('🖼 Мои фотографии')
        token = self.bot.dialog()['token']
        self.message('↩️ Отмена')
        with self.assertRaises(ValueError):
            self.callback('rights:'+token)

    def test_upload_attaches_to_intended_draft(self):
        self.upload_setup(draft=True)
        self.message(photo=True)
        self.callback('done:'+self.bot.dialog()['token'])
        self.assertEqual(self.store.get(self.id)['photo'],'file-a')
        self.assertEqual(self.bot.dialog(),{})

    def test_stale_upload_cannot_change_draft(self):
        self.upload_setup(draft=True)
        self.store.edit(self.id,text='Changed elsewhere')
        with self.assertRaises(ValueError):
            self.message(photo=True)
        self.assertIsNone(self.store.get(self.id)['photo'])

    def test_edit_button_plain_text_preserves_source(self):
        self.callback(f'edit:{self.id}:1')
        self.message('Новый заголовок')
        row = self.store.get(self.id)
        self.assertIn('https://example.org',row['text'])
        self.assertEqual(row['version'],2)
        self.assertEqual(self.bot.dialog(),{})

    def test_edit_stale_dialog_rejected(self):
        self.callback(f'edit:{self.id}:1')
        self.store.edit(self.id,text='Different version')
        with self.assertRaises(ValueError):
            self.message('Stale edit')
        self.assertEqual(self.store.get(self.id)['text'],'Different version')

    def test_owner_and_private_chat_required(self):
        self.callback(f'edit:{self.id}:1',user=2)
        self.callback(f'edit:{self.id}:1',chat=-100)
        self.message('🖼 Мои фотографии',user=2)
        self.message('🖼 Мои фотографии',chat=-100)
        self.assertEqual(self.bot.dialog(),{})

    def test_photo_replacement_revokes_approval(self):
        self.store.edit(self.id,photo='old',credit='Old credit')
        self.store.approve(self.id,2,1,1)
        self.store.add_photo('u','new','Татры','Иллюстрация.',1)
        self.callback(f'another:{self.id}:2')
        row = self.store.get(self.id)
        self.assertEqual(row['state'],'draft')
        self.assertIsNone(row['approved_by'])
        self.assertEqual(row['photo'],'new')

    def test_caption_matching_and_rotation(self):
        self.store.add_photo('one','first','Татры осенью','Иллюстрация.',1)
        self.store.add_photo('two','second','Италия','Иллюстрация.',1)
        self.bot.choose_photo(self.id)
        self.assertEqual(self.store.get(self.id)['photo'],'first')
        self.bot.choose_photo(self.id,exclude_current=True)
        self.assertEqual(self.store.get(self.id)['photo'],'second')

    def test_duplicate_upload_deduplicated(self):
        self.upload_setup()
        self.message(photo=True)
        self.message(photo=True)
        self.assertEqual(len(self.store.photos()),1)

    def test_expired_dialog(self):
        self.upload_setup()
        state = self.bot.dialog()
        state['expires'] = 0
        self.store.set('dialog',json.dumps(state))
        self.message(photo=True)
        self.assertEqual(self.store.photos(),[])

    def test_storage_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder+'/test.db')
            store.add_photo('one','first','Татры','Иллюстрация.',1)
            store.db.close()
            reopened = Store(folder+'/test.db')
            self.assertEqual(reopened.photos()[0]['file_id'],'first')
            reopened.db.close()

    def test_publish_disabled_remains_disabled(self):
        self.callback(f'publish:{self.id}:1')
        self.assertEqual(self.store.get(self.id)['state'],'draft')
        self.assertFalse(any(call.args[0]=='sendPhoto' for call in self.bot.api.call_args_list))

    def test_rewrite_uses_followup_text(self):
        self.callback(f'rewrite:{self.id}:1')
        self.message('Короче')
        self.bot.editor.rewrite.assert_called_once_with(self.id,'Короче')


if __name__ == '__main__':
    unittest.main()
