import time
import requests
import json
import argparse
import sys
import os
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from tqdm import tqdm


def get_items_list(session, cdn_list, url, retries, extensions, only_export, custom_path=None):
    extensions_list = extensions.split(',') if extensions is not None else []
       
    r = session.get(url)
    if r.status_code != 200:
        raise Exception(f"[-] HTTP error {r.status_code}")

    soup = BeautifulSoup(r.content, 'html.parser')
    is_bunkr = "| Bunkr" in soup.find('title').text
    
    if is_bunkr:
        items = []
        soup = BeautifulSoup(r.content, 'html.parser')
        boxes = soup.find_all('a', {'class': 'grid-images_box-link'})
        for box in boxes:
            items.append({'url': box['href'], 'size': -1})
        
        album_name = soup.find('h1', {'class': 'text-[24px]'}).text
        album_name = remove_illegal_chars(album_name[:album_name.index('\n')] if album_name.index('\n') > 0 else album_name)
    else:
        items = []
        items_dom = soup.find_all('a', {'class': 'image'})
        for item_dom in items_dom:
            items.append({'url': f"https://cyberdrop.me{item_dom['href']}", 'size': -1})
        album_name = remove_illegal_chars(soup.find('h1', {'id': 'title'}).text)

    download_path = get_and_prepare_download_path(custom_path, album_name)
    already_downloaded_url = get_already_downloaded_url(download_path)

    for item in items:
        item = get_real_download_url(session, cdn_list, item['url'], is_bunkr)
        if item is None:
            print(f"\t\t[-] Unable to find a download link")
            continue

        extension = get_url_data(item['url'])['extension']
        if ((extension in extensions_list or len(extensions_list) == 0) and (item['url'] not in already_downloaded_url)):
            if only_export:
                write_url_to_list(item['url'], download_path)
            else:
                for i in range(1, retries + 1):
                    try:
                        print(f"\t[+] Downloading {item['url']} (try {i}/{retries})")
                        download(session, item['url'], download_path, is_bunkr, item['name'] if not is_bunkr else None)
                        break
                    except requests.exceptions.ConnectionError as e:
                        if i < retries:
                            time.sleep(2)
                            pass
                        else:
                            raise e

    print(
        f"\t[+] File list exported in {os.path.join(download_path, 'url_list.txt')}" if only_export else f"\t[+] Download completed")
    return
    
def get_real_download_url(session, cdn_list, url, is_bunkr=True):

    if is_bunkr:
        url = url if 'https' in url else f'https://bunkr.sk{url}'
    else:
        url = url.replace('/f/','/api/f/')

    r = session.get(url)
    if r.status_code != 200:
        print(f"\t[-] HTTP error {r.status_code} getting real url for {url}")
        return None
        
    if is_bunkr:
        soup = BeautifulSoup(r.content, 'html.parser')
        source_dom = soup.find('source')
        images_dom = soup.find_all('img')
        links = soup.find_all('a',{'class': 'rounded-[5px]'})

        if source_dom is not None:
            return {'url': source_dom['src'], 'size': -1}
        if images_dom is not None:
            for image_dom in images_dom:
                if image_dom.attrs.get('data-lightbox') is not None:
                    return {'url': image_dom['src'], 'size': -1}
        if links is not None and len(links) > 0:
            url = get_cdn_file_url(session, cdn_list, url)
            return {'url': url, 'size': -1} if url is not None else None
    else:
        item_data = json.loads(r.content)
        return {'url': item_data['url'], 'size': -1, 'name': item_data['name']}


    return None

def get_cdn_file_url(session, cdn_list, gallery_url):

    if cdn_list is None:
        print(f"\t[-] CDN list is empty unable to download {gallery_url}")
        return None
    
    for cdn in cdn_list:
        url_to_test = f"https://{cdn}/{gallery_url[gallery_url.index('/d/')+3:]}"
        r = session.get(url_to_test)
        if r.status_code == 200:
            return url_to_test
        elif r.status_code == 404:
            continue
        elif r.status_code == 403:
            print(f"\t\t[-] DDoSGuard blocked request to {gallery_url}, skipping")
            return None
        else:
            print(f"\t\t[-] HTTP Error {r.status_code} for {gallery_url}, skipping")
            return None
        
    return None


def download(session, item_url, download_path, is_bunkr=False, file_name=None):

    file_name = get_url_data(item_url)['file_name'] if file_name is None else file_name
    final_path = os.path.join(download_path, file_name)

    with session.get(item_url, stream=True, timeout=5) as r:
        if r.status_code != 200:
            print(f"\t[-] Error downloading \"{file_name}\": {r.status_code}")
            return
        if r.url == "https://bnkr.b-cdn.net/maintenance.mp4":
            print(f"\t[-] Error downloading \"{file_name}\": Server is down for maintenance")

        file_size = int(r.headers.get('content-length', -1))
        with open(final_path, 'wb') as f:
            with tqdm(total=file_size, unit='iB', unit_scale=True, desc=file_name, leave=False) as pbar:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk is not None:
                        f.write(chunk)
                        pbar.update(len(chunk))

    if is_bunkr and file_size > -1:
        downloaded_file_size = os.stat(final_path).st_size
        if downloaded_file_size != file_size:
            print(f"\t[-] {file_name} size check failed, file could be broken\n")
            return

    mark_as_downloaded(item_url, download_path)

    return

def create_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://bunkr.sk/'
    })
    return session

def get_url_data(url):
    parsed_url = urlparse(url)
    return {'file_name': os.path.basename(parsed_url.path), 'extension': os.path.splitext(parsed_url.path)[1], 'hostname': parsed_url.hostname}

def get_and_prepare_download_path(custom_path, album_name):

    final_path = 'downloads' if custom_path is None else custom_path
    final_path = os.path.join(final_path, album_name) if album_name is not None else 'downloads'
    final_path = final_path.replace('\n', '')

    if not os.path.isdir(final_path):
        os.makedirs(final_path)

    already_downloaded_path = os.path.join(final_path, 'already_downloaded.txt')
    if not os.path.isfile(already_downloaded_path):
        with open(already_downloaded_path, 'x', encoding='utf-8'):
            pass

    return final_path

def write_url_to_list(item_url, download_path):

    list_path = os.path.join(download_path, 'url_list.txt')

    with open(list_path, 'a', encoding='utf-8') as f:
        f.write(f"{item_url}\n")

    return

def get_already_downloaded_url(download_path):

    file_path = os.path.join(download_path, 'already_downloaded.txt')

    if not os.path.isfile(file_path):
        return []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read().splitlines()

def mark_as_downloaded(item_url, download_path):

    file_path = os.path.join(download_path, 'already_downloaded.txt')
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(f"{item_url}\n")

    return

def get_cdn_list(session):
    r = session.get('https://status.bunkr.ru/')
    if r.status_code != 200:
        print(f"[-] HTTP Error {r.status_code} while getting cdn list")
        return None
    
    cdn_ret = []
    soup = BeautifulSoup(r.content, 'html.parser')
    cdn_list = soup.find_all('h2')
    if cdn_list is not None:
        cdn_list = cdn_list[1:]
        for cdn in cdn_list:
            cdn_ret.append(f"{cdn.text}.bunkr.ru")

    return cdn_ret

def remove_illegal_chars(string):
    return re.sub(r'[<>:"/\\|?*\']|[\0-\31]', "-", string).strip()
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser(sys.argv[1:])
    parser.add_argument("-u", help="Url to fetch", type=str, required=True)
    parser.add_argument("-r", help="Download retries", type=int, required=False, default=10)
    parser.add_argument("-e", help="Extensions to download (comma separated)", type=str)
    parser.add_argument("-p", help="Path to custom downloads folder")
    parser.add_argument("-w", help="Export url list (ex: for wget)", action="store_true")

    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')

    session = create_session()
    cdn_list = get_cdn_list(session)
    get_items_list(session, cdn_list, args.u, args.r, args.e, args.w, args.p)