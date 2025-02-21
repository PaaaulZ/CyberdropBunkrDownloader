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


def get_items_list(session, url, retries, extensions, only_export, custom_path=None):
    extensions_list = extensions.split(',') if extensions is not None else []
       
    r = session.get(url)
    if r.status_code != 200:
        raise Exception(f"[-] HTTP error {r.status_code}")

    soup = BeautifulSoup(r.content, 'html.parser')
    is_bunkr = "| Bunkr" in soup.find('title').text

    direct_link = False
    
    if is_bunkr:
        items = []
        soup = BeautifulSoup(r.content, 'html.parser')

        direct_link = soup.find('span', {'class': 'ic-videos'}) is not None or soup.find('div', {'class': 'lightgallery'}) is not None
        if direct_link:
            album_name = soup.find('h1', {'class': 'text-[20px]'})
            if album_name is None:
                album_name = soup.find('h1', {'class': 'truncate'})

            album_name = remove_illegal_chars(album_name.text)
            items.append(get_real_download_url(session, url, True))
        else:
            boxes = soup.find_all('a', {'class': 'after:absolute'})
            for box in boxes:
                items.append({'url': box['href'], 'size': -1})
            
            album_name = soup.find('h1', {'class': 'truncate'}).text
            album_name = remove_illegal_chars(album_name)
    else:
        items = []
        items_dom = soup.find_all('a', {'class': 'image'})
        for item_dom in items_dom:
            items.append({'url': f"https://cyberdrop.me{item_dom['href']}", 'size': -1})
        album_name = remove_illegal_chars(soup.find('h1', {'id': 'title'}).text)

    download_path = get_and_prepare_download_path(custom_path, album_name)
    already_downloaded_url = get_already_downloaded_url(download_path)

    for item in items:
        if not direct_link:
            item = get_real_download_url(session, item['url'], is_bunkr)
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

    print(f"\t[+] File list exported in {os.path.join(download_path, 'url_list.txt')}" if only_export else f"\t[+] Download completed")
    return
    
def get_real_download_url(session, url, is_bunkr=True):

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
        media_player_dom = soup.find('media-player')
        image_dom = soup.find('img', {'class': 'max-h-full'})
        link_dom = soup.find('a',{'class': 'ic-download-01'})

        if source_dom is not None:
            return {'url': source_dom['src'], 'size': -1}
        if media_player_dom is not None:
            return {'url': media_player_dom['src'], 'size': -1}
        if image_dom is not None:
            return {'url': image_dom['src'], 'size': -1}
        if link_dom is not None:
            url = get_cdn_file_url(session, link_dom['href'])
            return {'url': url, 'size': -1} if url is not None else None
    else:
        item_data = json.loads(r.content)
        return {'url': item_data['url'], 'size': -1, 'name': item_data['name']}

    return None

def get_cdn_file_url(session, download_page_url):

    r = session.get(download_page_url)
    if r.status_code != 200:
        print(f"\t\t[-] HTTP ERROR {r.status_code} getting direct CDN url")
        return None
    
    soup = BeautifulSoup(r.content, 'html.parser')
    download_btn = soup.find('a', {'class': 'ic-download-01'})
    return download_btn['href'] if download_btn is not None else None


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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
        'Referer': 'https://bunkr.sk/',
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

def remove_illegal_chars(string):
    return re.sub(r'[<>:"/\\|?*\']|[\0-\31]', "-", string).strip()
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser(sys.argv[1:])
    parser.add_argument("-u", help="Url to fetch", type=str, required=False, default=None)
    parser.add_argument("-f", help="File to list of URLs to download", required=False, type=str, default=None)
    parser.add_argument("-r", help="Amount of retries in case the connection fails", type=int, required=False, default=10)
    parser.add_argument("-e", help="Extensions to download (comma separated)", type=str)
    parser.add_argument("-p", help="Path to custom downloads folder")
    parser.add_argument("-w", help="Export url list (ex: for wget)", action="store_true")

    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')

    if args.u is None and args.f is None:
        print("[-] No URL or file provided")
        sys.exit(1)

    if args.u is not None and args.f is not None:
        print("[-] Please provide only one URL or file")
        sys.exit(1)

    session = create_session()

    if args.f is not None:
        with open(args.f, 'r', encoding='utf-8') as f:
            urls = f.read().splitlines()
        for url in urls:
            print(f"\t[-] Processing \"{url}\"...")
            get_items_list(session, url, args.r, args.e, args.w, args.p)
        sys.exit(0)
    else:
        get_items_list(session, args.u, args.r, args.e, args.w, args.p)
    sys.exit(0)
