import requests
import json
import argparse
import sys
import traceback
import os
from bs4 import BeautifulSoup
from urllib.parse import urlparse


def get_items_list(url, extensions, min_file_size, use_album_id, custom_path=None):
    extensions_list = extensions.split(',') if extensions is not None else []
    hostname = get_url_data(url)['hostname']

    r = requests.get(url)
    if r.status_code != 200:
        raise Exception(f"HTTP error {r.status_code}")

    soup = BeautifulSoup(r.content, 'html.parser')
    if hostname in ['bunkr.is', 'stream.bunkr.is']:
        item_urls = []
        album_or_file = 'file' if hostname == 'stream.bunkr.is' else 'album'
        json_data_element = soup.find("script", {"id": "__NEXT_DATA__"})
        json_data = json.loads(json_data_element.string)
        files = json_data['props']['pageProps']['album']['files'] if album_or_file == 'album' else [json_data['props']['pageProps']['file']]
        if album_or_file == 'file':
            item_urls = [f"{file['mediafiles']}/{file['name']}" for file in files if int(float(file['size'])) > (min_file_size * 1000)]
        else:
            item_urls = [f"{file['cdn'].replace('/cdn','/media-files')}/{file['name']}" for file in files if int(float(file['size'])) > (min_file_size * 1000)]
        album_name = json_data['props']['pageProps'][album_or_file]['name'] if not use_album_id else str(json_data['props']['pageProps'][album_or_file]['id'])
    else:
        items = soup.find_all('a', {'class': 'image'})
        item_urls = [item['href'] for item in items]
        album_name = soup.find('h1', {'id': 'title'}).text

    album_name = album_name.strip()

    for item_url in item_urls:
        extension = get_url_data(item_url)['extension']
        if extension in extensions_list or len(extensions_list) == 0:
            print(f"[+] Downloading {item_url}")
            download(item_url, custom_path, album_name, hostname == 'bunkr.is')


def download(item_url, custom_path, album_name=None, is_bunkr=False):
    final_path = 'downloads' if custom_path is None else os.path.join(custom_path, 'downloads')

    if not os.path.isdir(final_path):
        os.makedirs(final_path)

    if album_name is not None:
        download_path = os.path.join(final_path, album_name)
        if not os.path.isdir(download_path):
            os.mkdir(download_path)
    else:
        download_path = 'downloads'

    sHistoryFile = rf".\\{download_path}\\history.txt"
    try:
        file = open(sHistoryFile)
        lines = file.readlines()
        lHistory = [line.rstrip() for line in lines]
    except:
        print("History file created!")
        with open(sHistoryFile, 'w+') as file:
            lHistory = []

    if item_url in lHistory:
        print(f"item_url = {item_url} already in history - skipping!")
    else:
        file_name = get_url_data(item_url)['file_name']
        with requests.get(item_url, headers={'Referer': 'https://stream.bunkr.is/'} if is_bunkr else {}, stream=True) as r:
            with open(os.path.join(download_path, file_name), 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        # Write item to history when download is done
        with open(sHistoryFile, 'a') as history:
            history.write(item_url + "\n")

    return


def get_url_data(url):
    parsed_url = urlparse(url)
    return {'file_name': os.path.basename(parsed_url.path), 'extension': os.path.splitext(parsed_url.path)[1], 'hostname': parsed_url.hostname}


if __name__ == '__main__':

    parser = argparse.ArgumentParser(sys.argv[1:])
    parser.add_argument("-u", help="Url to fetch", type=str, required=True)
    parser.add_argument("-e", help="Extensions to download (comma separated)", type=str)
    parser.add_argument("-s", help="Minimum file size to download (in kilobytes, only for Bunkr)", type=int, const=0, default=0, nargs='?')
    parser.add_argument("-i", help="Use album id instead of album name for the folder name (only for Bunkr)", action="store_true")
    parser.add_argument("-p", help="Path to custom downloads folder")

    args = parser.parse_args()

    get_items_list(args.u, args.e, args.s, args.i, args.p)
