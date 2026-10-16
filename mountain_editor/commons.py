"""Conservative Commons image suggestions. Metadata checks are not a legal guarantee."""
import json
import os
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

LICENSES = {
    'CC BY 4.0': 'https://creativecommons.org/licenses/by/4.0/',
    'CC BY-SA 4.0': 'https://creativecommons.org/licenses/by-sa/4.0/',
    'CC0': 'https://creativecommons.org/publicdomain/zero/1.0/',
}
for version in ('2.0','2.5','3.0'):
    for code, name in (('by','CC BY'),('by-sa','CC BY-SA')):
        LICENSES[f'{name} {version}'] = f'https://creativecommons.org/licenses/{code}/{version}/'


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(value):
    parser = PlainText()
    parser.feed(str(value))
    return ' '.join(' '.join(parser.parts).split())


def units(value):
    return len(value.encode('utf-16-le')) // 2


def candidate(page, budget):
    infos = page.get('imageinfo',[])
    if not infos:
        return None
    info = infos[0]
    meta = info.get('extmetadata',{})
    def field(name):
        return plain(meta.get(name,{}).get('value',''))
    license = field('LicenseShortName')
    if license not in LICENSES:
        return None
    license_url = field('LicenseUrl').replace('http://','https://').rstrip('/')+'/'
    if license_url != LICENSES[license]:
        return None
    if field('Restrictions') or field('NonFree').lower() not in ('','false','0'):
        return None
    author = field('Artist')
    if not author or author.lower() in ('unknown','anonymous'):
        return None
    # Complex extra attribution conditions require manual review, not silent omission.
    if field('Attribution') or field('Permission'):
        return None
    original = field('Credit')
    if original.lower() in ('','own work'):
        original = ''
    elif not original.startswith(('https://','http://')) or any(c.isspace() for c in original):
        return None
    url = info.get('thumburl','')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in ('upload.wikimedia.org','thumb.wikimedia.org') or parsed.username:
        return None
    if info.get('mime') not in ('image/jpeg','image/png'):
        return None
    if info.get('width',0)<800 or info.get('height',0)<500:
        return None
    if max(info['width'],info['height']) / min(info['width'],info['height']) > 3:
        return None
    page_id = int(page['pageid'])
    source = f'https://commons.wikimedia.org/?curid={page_id}'
    credit = f'Иллюстрация, уменьшено. Фото: {author}\n{license}: {license_url}\n{source}'
    if license not in ('CC0','CC BY 4.0','CC BY-SA 4.0'):
        title = field('ObjectName') or page.get('title','').removeprefix('File:')
        if not title:
            return None
        credit = title+'\n'+credit
    if original:
        credit += '\n'+original
    if units(credit)>budget:
        return None  # Never truncate author or license information to fit a caption.
    return {'page_id':page_id,'image_url':url,'source':source,'credit':credit,
            'license':license,'license_url':license_url,'author':author,
            'title':page.get('title',''),'metadata':meta,
            'file_sha1':info.get('sha1'),'file_timestamp':info.get('timestamp')}


def search(query, budget, excluded=()):
    params = {'action':'query','format':'json','generator':'search','gsrnamespace':6,
              'gsrsearch':query[:160]+' filetype:bitmap','gsrlimit':40,
              'prop':'imageinfo','iiprop':'url|size|mime|extmetadata|sha1|timestamp','iiurlwidth':1280,
              'iiextmetadatalanguage':'en'}
    request = Request('https://commons.wikimedia.org/w/api.php?'+urlencode(params),headers={
        'User-Agent':os.getenv('COMMONS_USER_AGENT','NewsModerator/1.1 (https://github.com/davit2003/NewsModerator)')})
    with urlopen(request,timeout=20) as response:
        data = json.load(response)
    pages = sorted(data.get('query',{}).get('pages',{}).values(),key=lambda p:p.get('index',0))
    results = []
    for page in pages:
        if page.get('pageid') in excluded:
            continue
        photo = candidate(page,budget)
        if photo:
            results.append(photo)
    return results
