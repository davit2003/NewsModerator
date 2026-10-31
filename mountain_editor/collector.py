"""Bounded public-source collection. Failures remain visible, never become 'no news'."""
import hashlib
import json
import re
import time
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urljoin, urlunsplit, parse_qsl, urlencode

AGENT = 'MountainEditor/2.0 (+https://github.com/davit2003/NewsModerator)'
MAX_BYTES = 1500000


def canonical(url):
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None,443):
        raise ValueError('Only public HTTPS sources are supported')
    query = [(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k not in ('fbclid','gclid')]
    return urlunsplit(('https',p.netloc.lower(),p.path.rstrip('/'),urlencode(query),''))


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.skip = 0; self.main = 0; self.all = []; self.focus = []; self.links = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script','style','nav','footer','header','noscript'):
            self.skip += 1
        if tag in ('article','main'):
            self.main += 1
        if tag == 'a' and attrs.get('href') and not self.skip:
            self.links.append(attrs['href'])
    def handle_endtag(self, tag):
        if tag in ('script','style','nav','footer','header','noscript'):
            self.skip = max(0,self.skip-1)
        if tag in ('article','main'):
            self.main = max(0,self.main-1)
    def handle_data(self, data):
        if not self.skip and data.strip():
            self.all.append(data.strip())
            if self.main: self.focus.append(data.strip())
    def text(self):
        return ' '.join(self.focus or self.all)


def plain(html):
    p = TextParser(); p.feed(html); return p.text()


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        if new.scheme != 'https' or new.hostname != old.hostname:
            raise ValueError('Cross-host redirect skipped')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def fetch(url):
    req = urllib.request.Request(url,headers={'User-Agent':AGENT,'Accept':'text/html,application/rss+xml,application/atom+xml,application/xml'})
    with urllib.request.build_opener(SameHostRedirect).open(req,timeout=12) as r:
        media = r.headers.get_content_type()
        if not (media.startswith('text/') or 'xml' in media):
            raise ValueError('Non-text source skipped')
        body = r.read(MAX_BYTES+1)
        if len(body) > MAX_BYTES: raise ValueError('Source too large')
        return body.decode(r.headers.get_content_charset() or 'utf-8',errors='replace')


def date_of(value):
    try:
        d = datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError, AttributeError):
        try: d = parsedate_to_datetime(value)
        except (ValueError,TypeError): return None
    return d.replace(tzinfo=timezone.utc).timestamp() if d.tzinfo is None else d.timestamp()


def allowed(url):
    root = urlsplit(url)
    robots = urllib.robotparser.RobotFileParser()
    try:
        robots.parse(fetch(urlunsplit((root.scheme,root.netloc,'/robots.txt','',''))).splitlines())
    except urllib.error.HTTPError as e:
        return e.code == 404
    except Exception:
        return False
    return robots.can_fetch(AGENT,url)


def collect_source(source):
    url = source['url']; now = time.time()
    if not allowed(url): return [], 'robots unavailable or disallowed'
    raw = fetch(url)
    result = []
    if source['kind'] == 'feed':
        root = ET.fromstring(raw)
        entries = root.findall('.//item') or root.findall('{http://www.w3.org/2005/Atom}entry')
        for entry in entries[:12]:
            fields = {e.tag.split('}')[-1]:e for e in entry}
            def val(key):
                el = fields.get(key)
                return ''.join(el.itertext()).strip() if el is not None else ''
            link = val('link')
            if not link and fields.get('link') is not None: link = fields['link'].get('href','')
            try: link = canonical(link)
            except ValueError: continue
            stamp = date_of(val('pubDate') or val('published') or val('updated'))
            if not stamp or stamp < now-14*86400 or stamp > now+86400: continue
            text = plain(val('encoded') or val('content') or val('description') or val('summary'))
            if len(text) < 100: continue
            result.append(dict(url=link,title=val('title')[:240],body=text[:6000],published=stamp,kind='news'))
    elif source['kind'] == 'index':
        parser = TextParser(); parser.feed(raw)
        links=[]
        for href in parser.links:
            link=urljoin(url,href)
            if urlsplit(link).hostname != urlsplit(url).hostname: continue
            if re.search(r'\.(?:webp|jpg|jpeg|png|gif|pdf|zip|mp4)(?:[?#]|$)',link,re.I): continue
            if not re.search(source.get('link_pattern',r'/(?:20\d{2}/|[^/]+-\d+/?)'),link): continue
            try: link=canonical(link)
            except ValueError: continue
            if link not in links: links.append(link)
        for link in links[:3]:
            if not allowed(link): continue
            try:
                article=TextParser(); article.feed(fetch(link)); body=article.text()
                if len(body)>200:
                    result.append(dict(url=link,title=body[:160],body=body[:7000],published=None,kind='article'))
            except Exception: continue
    else:
        parser = TextParser(); parser.feed(raw); body = parser.text()
        if len(body) < 200: return [], 'insufficient extracted text'
        result.append(dict(url=canonical(url),title=source['name'],body=body[:10000],published=None,kind=source['kind']))
    for row in result:
        row.update(region=source['region'],retrieved=now,source=source['name'])
    return result, 'ok' if result else 'no recent extractable entries'


def collect():
    sources = json.loads(Path(__file__).resolve().parent.parent.joinpath('sources.json').read_text())
    def task(source):
        try: rows,status = collect_source(source)
        except Exception as e: rows,status = [],type(e).__name__
        return rows, {'source':source['name'],'status':status,'count':len(rows)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        pairs = list(pool.map(task,sources))
    return [row for rows,_ in pairs for row in rows], [status for _,status in pairs]
