import copy
import unittest
from unittest.mock import Mock, patch
from mountain_editor.commons import candidate, units
from mountain_editor.core import Store
from mountain_editor.bot import Bot


def page():
    return {'pageid':42,'title':'File:Tatra mountains.jpg','imageinfo':[{
        'thumburl':'https://upload.wikimedia.org/test.jpg','mime':'image/jpeg','width':2000,'height':1500,
        'extmetadata':{k:{'value':v} for k,v in {
            'Artist':'<a href="https://example.org">Jane Photographer</a>',
            'LicenseShortName':'CC BY 4.0','LicenseUrl':'https://creativecommons.org/licenses/by/4.0/'
        }.items()}}]}


class CommonsTests(unittest.TestCase):
    def test_attribution_complete(self):
        result = candidate(page(),400)
        self.assertIn('Jane Photographer',result['credit'])
        self.assertIn('https://creativecommons.org/licenses/by/4.0/',result['credit'])
        self.assertIn('curid=42',result['credit'])
        self.assertIn('Иллюстрация',result['credit'])

    def test_noncommercial_rejected(self):
        p = page()
        p['imageinfo'][0]['extmetadata']['LicenseShortName']['value'] = 'CC BY-NC 4.0'
        self.assertIsNone(candidate(p,400))

    def test_older_license_preserves_title(self):
        p = page()
        m = p['imageinfo'][0]['extmetadata']
        m['LicenseShortName']['value'] = 'CC BY-SA 3.0'
        m['LicenseUrl']['value'] = 'https://creativecommons.org/licenses/by-sa/3.0/'
        m['ObjectName'] = {'value':'Morning in the Tatras'}
        result = candidate(p,400)
        self.assertIn('Morning in the Tatras',result['credit'])
        self.assertIn('/by-sa/3.0/',result['credit'])

    def test_original_source_link_preserved(self):
        p = page()
        p['imageinfo'][0]['extmetadata']['Credit'] = {'value':'https://example.org/photo'}
        self.assertIn('https://example.org/photo',candidate(p,400)['credit'])

    def test_mismatched_license_rejected(self):
        p = page()
        p['imageinfo'][0]['extmetadata']['LicenseUrl']['value'] = 'https://example.org/license'
        self.assertIsNone(candidate(p,400))

    def test_extra_attribution_and_restrictions_rejected(self):
        for field in ('Restrictions','Attribution','Permission'):
            p = page()
            p['imageinfo'][0]['extmetadata'][field] = {'value':'Special requirement'}
            self.assertIsNone(candidate(p,400))

    def test_author_never_truncated(self):
        self.assertIsNone(candidate(page(),20))
        p = page()
        del p['imageinfo'][0]['extmetadata']['Artist']
        self.assertIsNone(candidate(p,400))

    def test_only_wikimedia_image_host(self):
        p = page()
        p['imageinfo'][0]['thumburl'] = 'https://example.org/test.jpg'
        self.assertIsNone(candidate(p,400))

    def test_wikimedia_thumbnail_host_supported(self):
        p = page()
        p['imageinfo'][0]['thumburl'] = 'https://thumb.wikimedia.org/wikipedia/commons/thumb/test.jpg'
        self.assertIsNotNone(candidate(p,400))

    def test_web_photo_freezes_file_and_license(self):
        store = Store(':memory:')
        id = store.add('story','Татры сегодня',[],'')
        store.set(f'image_query:{id}','Tatra Mountains')
        bot = Bot.__new__(Bot)
        bot.store,bot.owner = store,1
        bot.api = Mock(return_value={'photo':[{'file_id':'frozen-photo'}]})
        with patch('mountain_editor.moderation.commons.search',return_value=[candidate(page(),400)]):
            self.assertTrue(bot.web_photo(id))
        row = store.get(id)
        self.assertEqual(row['photo'],'frozen-photo')
        self.assertEqual(row['state'],'draft')
        self.assertTrue(store.setting(f'photo_evidence:{id}:{row["version"]}'))
        self.assertEqual(bot.api.call_args.kwargs['chat_id'],1)

    def test_failed_search_preserves_post(self):
        store = Store(':memory:')
        id = store.add('story','Татры',[],'')
        store.set(f'image_query:{id}','Tatra Mountains')
        bot = Bot.__new__(Bot)
        bot.store,bot.owner = store,1
        bot.tell = Mock()
        with patch('mountain_editor.moderation.commons.search',side_effect=TimeoutError):
            self.assertFalse(bot.web_photo(id))
        self.assertEqual(store.get(id)['version'],1)

    def test_edit_cannot_overflow_or_drop_credit(self):
        store = Store(':memory:')
        id = store.add('story','Short',[],'')
        store.edit(id,photo='file',credit='C'*300)
        with self.assertRaises(ValueError):
            store.edit(id,text='T'*850)
        self.assertEqual(store.get(id)['credit'],'C'*300)


if __name__ == '__main__':
    unittest.main()
