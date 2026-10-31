"""Conservative, persistent app allowance; not a provider billing meter."""
import math
import os
from datetime import datetime, timezone


class Budget:
    def __init__(self, store):
        self.store = store
        self.limit = min(18.0, max(0, float(os.getenv('AI_MONTHLY_BUDGET_USD', '18'))))
        self.db = store.db
        self.db.execute('''CREATE TABLE IF NOT EXISTS ai_costs (
            id INTEGER PRIMARY KEY, month TEXT NOT NULL, amount INTEGER NOT NULL,
            status TEXT NOT NULL)''')
        self.db.commit()

    @staticmethod
    def month():
        return datetime.now(timezone.utc).strftime('%Y-%m')

    def used(self):
        return self.db.execute('SELECT COALESCE(SUM(amount),0) FROM ai_costs WHERE month=?',
                               (self.month(),)).fetchone()[0] / 1000000

    def reserve(self, model, prompt, output, search):
        if model not in ('gpt-5.4-mini', 'gpt-5.4-mini-2026-03-17'):
            raise ValueError('Бюджет настроен для gpt-5.4-mini. Для другой модели сначала обновите тарифы в коде.')
        # Byte count upper-bounds text tokens. Search may expand the full context.
        # Two tool calls maximum; charge an additional full 128k search context per call.
        input_bound = 400000 if search else len(prompt.encode('utf-8')) + 2048
        estimate = (input_bound * .75 + output * 4.5) / 1000000
        if search:
            estimate += 2 * (.01 + 128000 * .75 / 1000000)
        amount = math.ceil(estimate * 1000000 * 1.2)  # price/rounding buffer
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.used() + amount / 1000000 > self.limit:
                raise ValueError('Месячный AI-бюджет исчерпан. Сохранённые материалы и публикация доступны; новые AI-запросы остановлены до следующего месяца UTC.')
            return self.db.execute('INSERT INTO ai_costs(month,amount,status) VALUES (?,?,?)',
                                   (self.month(), amount, 'reserved')).lastrowid

    def settle(self, id, data):
        usage = data.get('usage', {})
        if not all(isinstance(usage.get(k), int) and usage[k] >= 0 for k in ('input_tokens','output_tokens')):
            return  # missing/ambiguous usage keeps full reservation, including on failures
        count = sum(x.get('type') == 'web_search_call' for x in data.get('output', []))
        estimate = (usage['input_tokens'] * .75 + usage['output_tokens'] * 4.5) / 1000000
        estimate += count * (.01 + 128000 * .75 / 1000000)
        with self.db:
            self.db.execute('UPDATE ai_costs SET amount=?,status=? WHERE id=? AND status=?',
                            (math.ceil(estimate * 1200000), 'estimated', id, 'reserved'))

    def report(self):
        return (f'AI: ${self.used():.2f} / ${self.limit:.2f} за {self.month()} (UTC).\n'
                'Это консервативный учёт с резервами, не счёт OpenAI. Ошибки без данных о расходе сохраняют резерв.\n'
                'Общий ориентир: $30/месяц; $12 оставлено на Railway и запас. '
                'Расходы других приложений и до установки счётчика не включены.')
