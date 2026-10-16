import time
import unittest
from unittest.mock import Mock
from mountain_editor.core import Store
from mountain_editor.bot import Bot


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.s = Store(':memory:')
        self.id = self.s.add('story','Новость с источником', ['https://example.org/news'],'Relevant')
        self.s.edit(self.id,photo='file-id',credit='Фото: автор. Иллюстрация.')

    def approve(self):
        self.s.approve(self.id,self.s.get(self.id)['version'],1,1)

    def test_unauthorized(self):
        with self.assertRaises(ValueError):
            self.s.approve(self.id,2,2,1)

    def test_stale_button(self):
        self.s.edit(self.id,text='Изменено')
        with self.assertRaises(ValueError):
            self.s.approve(self.id,2,1,1)

    def test_edit_revokes_approval(self):
        self.approve()
        self.s.edit(self.id,text='Новая версия')
        self.assertFalse(self.s.claim(self.id))
        self.assertIsNone(self.s.get(self.id)['approved_by'])

    def test_duplicate_claim(self):
        self.approve()
        self.assertTrue(self.s.claim(self.id))
        self.assertFalse(self.s.claim(self.id))

    def test_expiry(self):
        with self.assertRaises(ValueError):
            self.s.approve(self.id,2,1,1,time.time()+90000)

    def test_photo_required(self):
        id = self.s.add('other','Текст',[],'')
        with self.assertRaises(ValueError):
            self.s.approve(id,1,1,1)

    def test_duplicates(self):
        self.assertIsNone(self.s.add('story','Повтор',[],''))

    def test_daily_budget(self):
        self.s.consume_call('2026-10-16',1)
        with self.assertRaises(ValueError):
            self.s.consume_call('2026-10-16',1)

    def test_network_ambiguity_never_retries(self):
        bot = Bot.__new__(Bot)
        bot.store,bot.live,bot.target = self.s,True,'test'
        bot.api = Mock(side_effect=TimeoutError)
        bot.tell = Mock()
        self.approve()
        bot.publish_due()
        bot.publish_due()
        self.assertEqual(bot.api.call_count,1)
        self.assertEqual(self.s.get(self.id)['state'],'uncertain')

    def test_success_records_message(self):
        bot = Bot.__new__(Bot)
        bot.store,bot.live,bot.target = self.s,True,'test'
        bot.api = Mock(return_value={'message_id':42})
        self.approve()
        bot.publish_due()
        self.assertEqual(self.s.get(self.id)['message_id'],42)


if __name__ == '__main__':
    unittest.main()
