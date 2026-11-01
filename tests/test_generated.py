import base64
import os
import unittest
from unittest.mock import patch
from mountain_editor.core import Store
from mountain_editor.budget import Budget
from mountain_editor.generated import generate

class GeneratedTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(':memory:')
        self.id=self.store.add('a','A nature story',[],'')

    def test_cached_image_and_shared_allowance(self):
        image=b'\x89PNG\r\n\x1a\nfixture'
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test'}),patch('mountain_editor.generated.post',return_value={'data':[{'b64_json':base64.b64encode(image).decode()}]}) as post:
            self.assertEqual(generate(self.store,self.id),image)
            self.assertEqual(generate(self.store,self.id),image)
            self.assertEqual(post.call_count,1)
            self.assertEqual(Budget(self.store).used(),.25)

    def test_failure_not_retried_and_budget_retained(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test'}),patch('mountain_editor.generated.post',side_effect=ValueError('unavailable')) as post:
            with self.assertRaises(ValueError): generate(self.store,self.id)
            with self.assertRaises(ValueError): generate(self.store,self.id)
            self.assertEqual(post.call_count,1)
            self.assertEqual(Budget(self.store).used(),.25)

    def test_budget_prevents_request(self):
        with patch.dict(os.environ,{'AI_MONTHLY_BUDGET_USD':'.1'}),patch('mountain_editor.generated.post') as post:
            with self.assertRaises(ValueError): generate(self.store,self.id)
            post.assert_not_called()
