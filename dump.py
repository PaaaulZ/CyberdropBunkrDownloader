import requests
import json
import argparse
import sys
import os
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse 
def get_items_list(url, extensions, only_export, custom_path=None, check_server_status=False):

    extensions_list = extensions.split(',') if extensions is not None else []
    hostname = get_url_data(url)['hostname']
       
    r = requests.get(url)
    if r.status_code != 200:
        raise Exception(f"HTTP error {r.status_code}")

    soup = BeautifulSoup(r.content, 'html.parser')
    broken_servers = check_bunkr_status() if check_server_status else []
    if hostname in ['bunkr.is', 'stream.bunkr.is', 'bunkr.ru', 'stream.bunkr.ru', 'bunkr.su', 'stream.bunkr.su']:
        items = []
        album_or_file = 'file' if hostname in ['stream.bunkr.is', 'stream.bunkr.ru', 'stream.bunkr.su'] else 'album'
        if album_or_file == 'album':
            soup = BeautifulSoup(r.content, 'html.parser')
            boxes = soup.find_all('a', {'class': 'grid-images_box-link'})
            for box in boxes:
                items.append({'url': box['href'].replace('/cdn','/media-files'), 'size': -1})
        
        album_name = remove_illegal_chars(soup.find('h1', {'class': 'text-[24px]'}).text)
    else:
        items = []
        items_dom = soup.find_all('a', {'class': 'image'})
        for item_dom in items_dom:
            items.append({'url': item_dom['href'], 'size': -1})
        album_name = remove_illegal_chars(soup.find('h1', {'id': 'title'}).text)

    download_path = get_and_prepare_download_path(custom_path, album_name)
    already_downloaded_url = get_already_downloaded_url(download_path)
    if not only_export:
        for item in items:
            extension = get_url_data(item['url'])['extension']
            if ((extension in extensions_list or len(extensions_list) == 0) and (item['url'] not in already_downloaded_url)):
                print(f"[+] Downloading {item['url']}")
                download(item['url'], download_path, broken_servers, item['size'], hostname in ['bunkr.ru', 'bunkr.is', 'bunkr.su'])
    else:
        export_list(items, download_path)
        return

def download(item_url, download_path, broken_servers, file_size, is_bunkr=False):

    file_name = get_url_data(item_url)['file_name']
    with requests.get(item_url, headers={'Referer': 'https://stream.bunkr.su/', 'User-Agent': 'Mozila/5.0'} if is_bunkr else {}, stream=True) as r:
        if r.url in ["https://static.bunkr.su/v/maintenance.mp4", "https://static.bunkr.is/v/maintenance.mp4", "https://static.bunkr.su/v/maintenance.mp4"]:
            print(f"\t[-] Error Downloading \"{file_name}\", server is under maintenance\n")
            return

        hostname = get_url_data(r.url)['hostname']
        if hostname in broken_servers and is_bunkr:
            print(f"\t[-] Server is under maintenance, {file_name} could be broken\n")

        final_path = os.path.join(download_path, file_name)
        with open(final_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        file_size = int(file_size)
        if is_bunkr and file_size > -1:
            downloaded_file_size = os.stat(final_path).st_size
            if downloaded_file_size != file_size:
                print(f"\t[-] {file_name} size check failed, file could be broken\n")
            return

    mark_as_downloaded(item_url, download_path)

    return

def get_url_data(url):
    parsed_url = urlparse(url)
    return {'file_name': os.path.basename(parsed_url.path), 'extension': os.path.splitext(parsed_url.path)[1], 'hostname': parsed_url.hostname}

def get_and_prepare_download_path(custom_path, album_name):

    final_path = 'downloads' if custom_path is None else os.path.join(custom_path, 'downloads')
    final_path = os.path.join(final_path, album_name) if album_name is not None else 'downloads'
    final_path = final_path.replace('\n', '')

    if not os.path.isdir(final_path):
        os.makedirs(final_path)

    already_downloaded_path = os.path.join(final_path, 'already_downloaded.txt')
    if not os.path.isfile(already_downloaded_path):
        with open(already_downloaded_path, 'x', encoding='utf-8'):
            pass

    return final_path

def export_list(item_urls, download_path):

    list_path = os.path.join(download_path, 'url_list.txt')

    with open(list_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(item_urls))

    print(f"[+] File list exported in {list_path}")

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

def check_bunkr_status():
   
    broken_servers = []

    r = requests.get("https://status.bunkr.ru/")
    if r.status_code != 200:
        raise Exception(f"HTTP error {r.status_code}")

    soup = BeautifulSoup(r.content, 'html.parser')
    els = soup.find_all("div", {"class": "column"})
    for el in els:
        childrenList = list(el.children)
        server = childrenList[1].text
        status = childrenList[3].text
        if status not in ["Operational", "Degraded performance"]:
            rr = re.search(r'server #[0-9]+ \((.*?)\)', server)
            server = rr.group(1).replace('cdn', 'media-files')
            broken_servers.append(server)

    return broken_servers  

def remove_illegal_chars(string):
    return re.sub(r"[<>:/\\|?*\"]|[\0-\31]", "-", string)
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser(sys.argv[1:])
    parser.add_argument("-u", help="Url to fetch", type=str, required=True)
    parser.add_argument("-e", help="Extensions to download (comma separated)", type=str)
    parser.add_argument("-p", help="Path to custom downloads folder")
    parser.add_argument("-w", help="Export url list (ex: for wget)", action="store_true")
    parser.add_argument("-css", help="Check server status before downloading",action="store_true")

    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    get_items_list(args.u, args.e, args.w, args.p, args.css)
