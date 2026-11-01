import json
import os
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from mountain_editor.core import Store
from mountain_editor.inbox import Inbox
from mountain_editor.budget import Budget
from mountain_editor.collector import collect_source, canonical
from mountain_editor.bot import Bot
from mountain_editor.providers import Provider


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.s=Store(':memory:'); self.p=Mock(name='provider'); self.p.name='openai'
        self.box=Inbox(self.s,self.p,'brief')
        self.item=dict(title='Почему горы меняют цвет?',summary='Короткая история о природе.',
            source_url='https://tpn.gov.pl/story?utm_source=openai', evidence='Source-supported facts. '*12,
            category='nature',region='tatras',freshness='evergreen',score=9,verified=True,event_key='mountain leaf colours')

    def test_news_seven_day_cutoff(self):
        from datetime import datetime, timezone
        old=datetime.fromtimestamp(time.time()-8*86400,timezone.utc).isoformat()
        self.assertFalse(self.box.add({**self.item,'freshness':'news','published_at':old},[self.item['source_url']]))
        recent=datetime.fromtimestamp(time.time()-6*86400,timezone.utc).isoformat()
        self.assertTrue(self.box.add({**self.item,'freshness':'news','published_at':recent},[self.item['source_url']]))
        self.assertLessEqual(self.box.rows()[0]['expires'],time.time()+86400)

    def test_empty_news_triggers_learning_search(self):
        self.p.call.side_effect=[(json.dumps({'items':[]}),[]),(json.dumps({'items':[self.item]}),[self.item['source_url']])]
        with patch('mountain_editor.inbox.collect',return_value=([],[])):
            self.box.refresh()
        self.assertEqual(self.p.call.call_count,2)
        self.assertEqual(self.box.rows()[0]['freshness'],'evergreen')

    def test_tracking_links_deduplicate(self):
        self.assertTrue(self.box.add(self.item,['https://tpn.gov.pl/story']))
        self.assertFalse(self.box.add({**self.item,'source_url':'https://tpn.gov.pl/story'},['https://tpn.gov.pl/story']))
        self.assertEqual(self.box.rows()[0]['url'],'https://tpn.gov.pl/story')

    def test_no_unverified_or_uncited_ideas(self):
        self.assertFalse(self.box.add(self.item,['https://tpn.gov.pl/other']))
        self.assertFalse(self.box.add({**self.item,'verified':False},[self.item['source_url']]))
        self.assertFalse(self.box.add({**self.item,'score':4},[self.item['source_url']]))

    def test_draft_is_idempotent(self):
        self.box.add(self.item,[self.item['source_url']])
        self.p.call.return_value=(json.dumps({'publishable':True,'text':'Короткая история.','image_query':'Tatry autumn'}),[])
        id=self.box.draft(self.box.rows()[0]['id'])
        self.assertEqual(self.box.draft(1),id)
        self.assertEqual(self.p.call.call_count,1)
        self.assertFalse(self.box.rows())

    def test_skipped_and_expired_not_shown(self):
        self.box.add(self.item,[self.item['source_url']]); self.box.skip(1)
        self.assertFalse(self.box.rows())
        with self.assertRaises(ValueError): self.box.draft(1)

    def test_failed_refresh_preserves_inbox_and_diagnostics(self):
        self.box.add(self.item,[self.item['source_url']])
        self.p.call.side_effect=ValueError('AI unavailable')
        with patch('mountain_editor.inbox.collect',return_value=([],[{'source':'a','status':'TimeoutError','count':0}])):
            report=self.box.refresh()
            self.assertIn('AI unavailable',report)
            self.assertEqual(len(self.box.rows()),1)
            self.box.refresh()
        self.assertEqual(self.p.call.call_count,1)

    def test_feed_date_and_content(self):
        from email.utils import formatdate
        feed=f'<rss><channel><item><title>Title</title><link>https://tpn.gov.pl/new</link><pubDate>{formatdate(usegmt=True)}</pubDate><description>{"Nature facts. "*20}</description></item><item><title>old</title><pubDate>Mon, 01 Jan 2001 00:00:00 GMT</pubDate><link>https://tpn.gov.pl/old</link></item></channel></rss>'
        with patch('mountain_editor.collector.allowed',return_value=True),patch('mountain_editor.collector.fetch',return_value=feed):
            rows,status=collect_source({'url':'https://tpn.gov.pl/feed','name':'Example','kind':'feed','region':'tatras'})
        self.assertEqual(status,'ok'); self.assertEqual(len(rows),1)

    def test_index_skips_images_and_fetches_article(self):
        html='<main><a href="/story-123/">Story</a><a href="/image-2026.webp">Image</a></main>'
        article='<article>'+('Interesting mountain facts. '*20)+'</article>'
        with patch('mountain_editor.collector.allowed',return_value=True),patch('mountain_editor.collector.fetch',side_effect=[html,article]) as fetch:
            rows,status=collect_source({'url':'https://tpn.gov.pl/','name':'Example','kind':'index','region':'tatras'})
        self.assertEqual(fetch.call_count,2)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['url'],'https://tpn.gov.pl/story-123')

    def test_explicit_text_only_revokes_approval_and_publishes_message(self):
        id=self.s.add('x','Story',[],'')
        self.s.edit(id,photo='file',credit='Author')
        self.s.approve(id,2,1,1)
        self.s.edit(id,photo=None,credit=None,text_only=1)
        self.assertFalse(self.s.claim(id))
        self.s.approve(id,3,1,1)
        bot=Bot.__new__(Bot); bot.store=self.s; bot.live=True; bot.target='group'
        bot.api=Mock(return_value={'message_id':12}); bot.tell=Mock()
        bot.publish_due()
        self.assertEqual(bot.api.call_args.args[0],'sendMessage')
        self.assertEqual(self.s.get(id)['state'],'published')


class BudgetTests(unittest.TestCase):
    def test_persistent_reservation_and_cap(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'AI_MONTHLY_BUDGET_USD':'.01'}):
            path=d+'/editor.db'; s=Store(path); b=Budget(s)
            b.reserve('gpt-5.4-mini','small',128,False)
            used=b.used(); s.db.close()
            b=Budget(Store(path)); self.assertEqual(b.used(),used)
            with self.assertRaises(ValueError): b.reserve('gpt-5.4-mini','search',3500,True)
            self.assertEqual(b.used(),used)

    def test_missing_usage_retains_reservation(self):
        b=Budget(Store(':memory:')); id=b.reserve('gpt-5.4-mini','abc',1000,True)
        old=b.used(); b.settle(id,{}); self.assertEqual(b.used(),old)
        b.settle(id,{'usage':{'input_tokens':100,'output_tokens':100},'output':[]})
        self.assertLess(b.used(),old)

    def test_month_reset_unknown_model_and_max_ceiling(self):
        with patch.dict(os.environ,{'AI_MONTHLY_BUDGET_USD':'999'}):
            b=Budget(Store(':memory:')); self.assertEqual(b.limit,18)
        b.reserve('gpt-5.4-mini','abc',1000,False)
        with patch.object(Budget,'month',return_value='2099-01'): self.assertEqual(b.used(),0)
        with self.assertRaises(ValueError): b.reserve('unknown','abc',1000,False)

    def test_provider_bounds_tools_and_records_usage(self):
        with patch.dict(os.environ,{'AI_PROVIDER':'openai','AI_MODEL':'gpt-5.4-mini','OPENAI_API_KEY':'test'}):
            s=Store(':memory:'); p=Provider(s)
            with patch('mountain_editor.providers.post',return_value={'status':'completed','usage':{'input_tokens':100,'output_tokens':100},'output':[]}) as post:
                p.call('Find stories',search=True)
                self.assertEqual(post.call_args.args[1]['max_tool_calls'],2)
                self.assertGreater(Budget(s).used(),0)


if __name__=='__main__': unittest.main()
