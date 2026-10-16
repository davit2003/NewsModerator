import json
import sqlite3
import time
from pathlib import Path


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS drafts (
          id INTEGER PRIMARY KEY, story_key TEXT UNIQUE, text TEXT NOT NULL,
          sources TEXT NOT NULL, reason TEXT NOT NULL, photo TEXT, credit TEXT,
          version INTEGER NOT NULL DEFAULT 1, state TEXT NOT NULL DEFAULT 'draft',
          expires REAL NOT NULL, due REAL, approved_by INTEGER, approved_version INTEGER,
          message_id INTEGER, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS usage (day TEXT PRIMARY KEY, calls INTEGER NOT NULL);
        ''')
        # A crash after sending but before recording success is ambiguous. Never resend automatically.
        self.db.execute("UPDATE drafts SET state='uncertain' WHERE state='publishing'")
        self.db.commit()

    def get(self, id):
        row = self.db.execute('SELECT * FROM drafts WHERE id=?', (id,)).fetchone()
        if row is None:
            raise ValueError('Черновик не найден')
        return dict(row)

    def setting(self, key, default=''):
        row = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def set(self, key, value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, str(value)))

    def add(self, key, text, sources, reason, ttl=86400):
        self.validate_text(text)
        with self.db:
            cur = self.db.execute('''INSERT OR IGNORE INTO drafts
                (story_key,text,sources,reason,expires,created) VALUES (?,?,?,?,?,?)''',
                (key, text, json.dumps(sources, ensure_ascii=False), reason, time.time()+ttl, time.time()))
            return cur.lastrowid if cur.rowcount else None

    @staticmethod
    def validate_text(text):
        if not isinstance(text, str) or not text.strip() or len(text.encode('utf-16-le'))//2 > 850:
            raise ValueError('Текст должен содержать 1–850 символов UTF-16 (включая ссылки)')

    def edit(self, id, **changes):
        if set(changes) - {'text', 'photo', 'credit'}:
            raise ValueError('Invalid edit')
        if 'text' in changes:
            self.validate_text(changes['text'])
        with self.db:
            row = self.get(id)
            if row['state'] not in ('draft', 'approved'):
                raise ValueError('Этот черновик уже закрыт')
            fields = ','.join(f'{key}=?' for key in changes)
            self.db.execute(f'''UPDATE drafts SET {fields},version=version+1,state='draft',
                due=NULL,approved_by=NULL,approved_version=NULL WHERE id=?''', (*changes.values(), id))

    def approve(self, id, version, user, owner, due=None):
        if user != owner:
            raise ValueError('Нет доступа')
        now = time.time()
        due = now if due is None else due
        if due < now - 5:
            raise ValueError('Выберите время в будущем')
        with self.db:
            row = self.get(id)
            if row['state'] != 'draft' or row['version'] != version:
                raise ValueError('Откройте актуальный предпросмотр')
            if row['expires'] <= max(now, due):
                raise ValueError('Новость устарела или истечёт до публикации. Найдите свежий источник.')
            if not row['photo'] or not row['credit']:
                raise ValueError('Сначала добавьте фото с разрешением на использование и подписью')
            if len((row['text']+'\n\n'+row['credit']).encode('utf-16-le'))//2 > 1024:
                raise ValueError('Слишком длинная подпись к фото')
            self.db.execute("UPDATE drafts SET state='approved',due=?,approved_by=?,approved_version=? WHERE id=?",
                            (due,user,version,id))

    def claim(self, id):
        with self.db:
            cur = self.db.execute("""UPDATE drafts SET state='publishing' WHERE id=? AND state='approved'
                AND approved_version=version AND due<=? AND expires>?""", (id,time.time(),time.time()))
            return cur.rowcount == 1

    def finish(self, id, message_id=None):
        with self.db:
            self.db.execute("UPDATE drafts SET state=?,message_id=? WHERE id=? AND state='publishing'",
                            ('published' if message_id else 'uncertain', message_id,id))

    def reject(self, id, version):
        with self.db:
            self.db.execute("UPDATE drafts SET state='rejected' WHERE id=? AND version=? AND state IN ('draft','approved')", (id,version))

    def recent(self, limit=20):
        return [dict(r) for r in self.db.execute('SELECT * FROM drafts ORDER BY id DESC LIMIT ?', (limit,))]

    def consume_call(self, day, limit):
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO usage VALUES (?,0)', (day,))
            cur = self.db.execute('UPDATE usage SET calls=calls+1 WHERE day=? AND calls<?', (day,limit))
            if not cur.rowcount:
                raise ValueError('Достигнут дневной лимит AI-запросов')
