import io
import json
import unittest
import urllib.error
from unittest.mock import patch
from mountain_editor.providers import APIError, post, parse_json


class ProviderErrorTests(unittest.TestCase):
    def test_quota_error_is_actionable_and_redacted(self):
        body = json.dumps({'error':{'code':'insufficient_quota','message':'private-key-secret'}}).encode()
        error = urllib.error.HTTPError('https://api.openai.com/v1/responses',429,'error',{},io.BytesIO(body))
        with patch('urllib.request.urlopen',side_effect=error):
            with self.assertRaises(APIError) as caught:
                post('https://api.openai.com/v1/responses',{})
        self.assertIn('insufficient_quota',str(caught.exception))
        self.assertNotIn('private-key-secret',str(caught.exception))

    def test_telegram_token_never_appears(self):
        url='https://api.telegram.org/botSECRET/sendMessage'
        error=urllib.error.HTTPError(url,400,'Bad Request',{},io.BytesIO(b'{}'))
        with patch('urllib.request.urlopen',side_effect=error):
            with self.assertRaises(APIError) as caught:
                post(url,{})
        self.assertNotIn('SECRET',str(caught.exception))
        self.assertIn('Telegram',str(caught.exception))

    def test_unknown_provider_code_not_echoed(self):
        self.assertNotIn('SECRET',str(APIError('OpenAI',400,'SECRET')))

    def test_bad_model_error(self):
        self.assertIn('AI_MODEL',str(APIError('OpenAI',404,'model_not_found')))

    def test_invalid_json_actionable(self):
        with self.assertRaisesRegex(ValueError,'формат'):
            parse_json('invalid output')


if __name__ == '__main__':
    unittest.main()
