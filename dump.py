import requests
import json
import argparse
import sys
import os
import re
import time
from tenacity import retry, wait_fixed, retry_if_exception_type, stop_after_attempt
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from tqdm import tqdm
from datetime import datetime
from enum import StrEnum

BUNKR_SIGN_API_URL = "https://glb-apisign.cdn.cr/sign"
BUNKR_METADATA_API_URL = "https://dl.bunkr.cr/api/_001_v2"

CYBERDROP_METADATA_API_URL_BASE = "https://api.cyberdrop.cr/api/file/info"
CYBERDROP_AUTH_API_URL_BASE = "https://api.cyberdrop.cr/api/file/auth"

MAX_RETRIES = 10

class SUPPORTED_SITES(StrEnum):
    BUNKR = 'bunkr'
    CYBERDROP = 'cyberdrop'

class Options:

    extensions = []
    only_export = False
    custom_path = None
    date_before = None
    date_after = None

    def __init__(self, extensions, only_export, custom_path, date_before, date_after):
        self.extensions = extensions
        self.only_export = only_export
        self.custom_path = custom_path
        self.date_before = date_before
        self.date_after = date_after
        return

class UrlData:

    file_name = None
    file_extension = None
    url_hostname = None

    def __init__(self, url):
        parsed_url = urlparse(url)
        self.file_name = os.path.basename(parsed_url.path)
        self.file_extension = os.path.splitext(parsed_url.path)[1]
        self.url_hostname = parsed_url.hostname
        return

def bunkr_get_items(soup, session, url, is_direct_link, options):
    items = []

    if is_direct_link:
        album_name = soup.find('h1', {'class': 'text-[20px]'})
        if album_name is None:
            album_name = soup.find('h1', {'class': 'truncate'})

        album_name = remove_illegal_chars(album_name.text)
        items.append(get_real_download_url(session, url, True))
    else:
        theItems = soup.find_all('div', {'class': 'theItem'})
        for theItem in theItems:
            if options.date_before is not None or options.date_after is not None:
                date_span = theItem.find('span', {'class': 'ic-clock'})
                if not is_date_in_range(date_span.text, options.date_before, options.date_after):
                    continue

            box = theItem.find('a', {'class': 'after:absolute'})
            items.append({'url': box['href'], 'size': -1, 'name': theItem.find('p').text})

    return items

def cyberdrop_get_items(soup):
    items = []

    items_dom = soup.find_all('a', {'class': 'image'})
    for item_dom in items_dom:
        items.append({'url': f"https://cyberdrop.cr{item_dom['href']}", 'name': item_dom['data-src'], 'size': -1})

    return items

def prepare_download_items(items, session, is_direct_link, website, options, download_path, already_downloaded_url):
    for item in items:
        if not is_direct_link:
            item = get_real_download_url(session, item['url'], website, item['name'])

        if item is None:
            print(f"\t\t\t[-] Unable to find a download link")
            continue

        url_data = UrlData(item['url'])

        if ((url_data.file_extension in options.extensions or len(options.extensions) == 0) and (item['url'][:item['url'].index('?') if '?' in item['url'] else len(item['url'])] not in already_downloaded_url)):
            if options.only_export:
                write_url_to_list(item['url'], download_path)
            else:
                download(session, item['url'], download_path, website, item['name'])
    return

def get_website_from_page_title(page_title):
    if "| Bunkr" in page_title:
        return SUPPORTED_SITES.BUNKR
    elif "| CyberDrop" in page_title:
        return SUPPORTED_SITES.CYBERDROP

    return None

def get_items_list(session, url, options, is_last_page=True):
    items = []
       
    r = session.get(url)
    if r.status_code != 200:
        raise Exception(f"[-] HTTP error {r.status_code}")

    soup = BeautifulSoup(r.content, 'html.parser')
    page_title = soup.find('title').text

    website = get_website_from_page_title(page_title)

    is_direct_link = soup.find('span', {'class': 'ic-videos'}) is not None or soup.find('div', {'class': 'lightgallery'}) is not None

    album_name = None

    if website == SUPPORTED_SITES.BUNKR:
        items = bunkr_get_items(soup, session, url, is_direct_link, options)
        album_name = remove_illegal_chars(soup.find('h1', {'class': 'truncate'}).text)
    elif website == SUPPORTED_SITES.CYBERDROP:
        items = cyberdrop_get_items(soup)
        album_name = remove_illegal_chars(soup.find('h1', {'id': 'title'}).text)

    download_path = get_and_prepare_download_path(options.custom_path, album_name)
    already_downloaded_url = get_already_downloaded_urls(download_path)

    prepare_download_items(items, session, is_direct_link, website, options, download_path, already_downloaded_url)

    pagination = soup.find('nav', {'class': 'pagination'})
    if pagination is not None:
        current_page = int(pagination.find('span', {'class': 'active'}).text)
        page_links = [a for a in pagination.find_all('a') if a.text.strip().isdigit()]
        last_page = int(page_links[-1].text) if page_links else current_page

        if int(current_page) < int(last_page):
            url_next_page = None
            print(f"[!] Downloading page ({int(current_page)+1}/{last_page})")
            if re.search(r'([?&])page=\d+', url):
                url_next_page = re.sub(r'([?&])page=\d+', r'\1page={}'.format(current_page+1), url)
            else:
                url_next_page = f"{url}{'&' if '?' in url else '?'}page={(current_page+1)}"

            get_items_list(session, url_next_page, options, is_last_page=(int(current_page) == int(last_page)))

    if is_last_page:
        print(f"\t[+] File list exported in {os.path.join(download_path, 'url_list.txt')}" if options.only_export else f"\t[+] Download completed")    

    return

def cyberdrop_get_metadata(slug, session):
    r = session.get(f"{CYBERDROP_METADATA_API_URL_BASE}/{slug}")
    if r.status_code != 200:
        print(f"\t\t[-] HTTP error {r.status_code} getting metadata for item {slug}")
        return None

    return json.loads(r.content)

def cyberdrop_get_real_url(slug, session):
    r = session.get(f"{CYBERDROP_AUTH_API_URL_BASE}/{slug}")
    if r.status_code != 200:
        print(f"\t\t[-] HTTP error {r.status_code} getting real url for item {slug}")
        return None

    signed_data = json.loads(r.content)

    return signed_data['url']
    
def get_real_download_url(session, url, website, item_name=None):
    if website == SUPPORTED_SITES.BUNKR:
        url = url if 'https' in url else f'https://bunkr.sk{url}'

        r = session.get(url)
        if r.status_code != 200:
            print(f"\t\t[-] HTTP error {r.status_code} getting real url for {url}")
            return None
        
        soup = BeautifulSoup(r.content, 'html.parser')

        btnMaintenance = soup.find('button', {'title': 'Server under maintenance'})

        if btnMaintenance is not None:
            if item_name is None:
                item_name = soup.find('title').text.replace(' | Bunkr', '').strip()
            print(f"\t\t[-] Error downloading \"{item_name}\": Server is down for maintenance")
            return None
        real_url = bunkr_get_real_url(session, soup.find(attrs={'data-file-id': True})['data-file-id'])
        if real_url is None:
            return None
        
        return {'url': real_url['url'], 'size': -1, 'name': item_name if item_name is not None else real_url['name']}
    elif website == SUPPORTED_SITES.CYBERDROP:
        slug = url.split('/')[-1]

        real_url = cyberdrop_get_real_url(slug, session)
        metadata = cyberdrop_get_metadata(slug, session)

        return {'url': real_url, 'size': metadata['size'], 'name': metadata['name']}
        
@retry(retry=retry_if_exception_type(requests.exceptions.ConnectionError), wait=wait_fixed(2), stop=stop_after_attempt(MAX_RETRIES))
def download(session, item_url, download_path, website, file_name=None):

    url_data = UrlData(item_url)
    file_name = url_data.file_name if file_name is None else file_name

    final_path = os.path.join(download_path, file_name)

    if os.path.exists(final_path):
        file_name = f"{int(time.time())}_{file_name}"


    with session.get(item_url, stream=True, timeout=5) as r:
        print(f"\t[+] Downloading {item_url} ({file_name})")
        if r.status_code != 200:
            print(f"\t\t[-] Error downloading \"{file_name}\": {r.status_code}")
            return

        file_size = int(r.headers.get('content-length', -1))
        with open(final_path, 'wb') as f:
            with tqdm(total=file_size, unit='iB', unit_scale=True, desc=file_name, leave=False) as pbar:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk is not None:
                        f.write(chunk)
                        pbar.update(len(chunk))

    if website == SUPPORTED_SITES.BUNKR and file_size > -1:
        downloaded_file_size = os.stat(final_path).st_size
        if downloaded_file_size != file_size:
            print(f"\t[-] {file_name} size check failed, file could be broken\n")
            return

    mark_url_as_downloaded(item_url, download_path)

    return

def create_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
        'Referer': 'https://bunkr.sk/',
    })
    return session

def get_and_prepare_download_path(default_path, album_name):

    final_path = os.path.join(default_path, album_name) if album_name is not None else 'downloads'
    final_path = final_path.replace('\n', '')

    if not os.path.isdir(final_path):
        os.makedirs(final_path)

    already_downloaded_path = os.path.join(final_path, 'already_downloaded.txt')
    if not os.path.isfile(already_downloaded_path):
        open(already_downloaded_path, 'w', encoding='utf-8').close()

    return final_path

def write_url_to_list(item_url, download_path):

    list_path = os.path.join(download_path, 'url_list.txt')

    with open(list_path, 'a', encoding='utf-8') as f:
        f.write(f"{item_url}\n")

    return

def get_already_downloaded_urls(download_path):

    file_path = os.path.join(download_path, 'already_downloaded.txt')

    if not os.path.isfile(file_path):
        return []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read().splitlines()

def mark_url_as_downloaded(item_url, download_path):

    file_path = os.path.join(download_path, 'already_downloaded.txt')
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(f"{item_url[:item_url.index('?') if '?' in item_url else len(item_url)]}\n")

    return

def remove_illegal_chars(string):
    return re.sub(r'[<>:"/\\|?*\']|[\0-\31]', "-", string).strip()

def bunkr_get_real_url(session, file_id):

    r = session.post(BUNKR_METADATA_API_URL, json={'id': file_id})
    if r.status_code != 200:
        print(f"\t\t[-] HTTP ERROR {r.status_code} getting download metadata")
        return None

    meta = json.loads(r.content)
    media_path = meta['path']

    signed = bunkr_get_signed_params(session, media_path)
    if signed is None:
        return None

    return {'url': f"{meta['mediafiles']}{media_path}?token={signed['token']}&ex={signed['ex']}{'&n=' + meta.get('original') if meta.get('original') is not None else ''}", 'name': meta.get('original')}

def bunkr_get_signed_params(session, path):

    r = session.get(BUNKR_SIGN_API_URL, params={'path': path})
    if r.status_code != 200:
        print(f"\t\t[-] HTTP ERROR {r.status_code} signing download url")
        return None

    return json.loads(r.content)

def date_argument_type(date_string):
    try:
        return datetime.strptime(date_string, '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        raise argparse.ArgumentTypeError("Invalid date format. Use: yyyy-mm-ddThh:mm:ss")
    
def is_date_in_range(date_string, date_before, date_after):
    try:
        bunkr_date = datetime.strptime(date_string, '%H:%M:%S %d/%m/%Y')
        date_before = datetime.max if date_before is None else date_before
        date_after = datetime.min if date_after is None else date_after

        return bunkr_date <= date_before and bunkr_date >= date_after

    except ValueError:
        print(f"\t[-] Invalid file date {date_string}")
        return False

def main():
    parser = argparse.ArgumentParser(sys.argv[1:])

    required_args = parser.add_mutually_exclusive_group(required=True)
    required_args.add_argument("-u", help="Url to fetch", type=str, default=None)
    required_args.add_argument("-f", help="File containing list of URLs to download", type=str, default=None)

    parser.add_argument("-r", help="Number of retries in case the connection fails", type=int, required=False, default=10)
    parser.add_argument("-e", help="Extensions to download (comma separated)", type=str)
    parser.add_argument("-p", help="Path to custom downloads folder", default='downloads')
    parser.add_argument("-w", help="Export url list (ex: for wget)", action="store_true")
    parser.add_argument("--before", help="Export only files before this date", type=date_argument_type, default=None)
    parser.add_argument("--after", help="Export only files after this date", type=date_argument_type, default=None)

    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')

    session = create_session()

    global MAX_RETRIES
    MAX_RETRIES = args.r

    options = Options(args.e.split(',') if args.e is not None else [], args.w, args.p, args.before, args.after)

    if args.f is not None:
        with open(args.f, 'r', encoding='utf-8') as f:
            urls = f.read().splitlines()

        for url in urls:
            print(f"\t[-] Processing \"{url}\"...")
            get_items_list(session, url, options)
    else:
        get_items_list(session, args.u, options)
        
    return
    
if __name__ == '__main__':
    main()
