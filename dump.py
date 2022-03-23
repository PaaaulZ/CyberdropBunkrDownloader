from distutils import extension
import requests
from bs4 import BeautifulSoup
import argparse
import sys
import os
from os.path import splitext
from urllib.parse import urlparse 


def get_items_list(url, extensions):

    extensions_list = []
    if extensions is not None and extensions != "":
        extensions_list = extensions.split(',')

    r = requests.get(url)
    if r.status_code != 200:
        raise Exception(f"HTTP error {r.status_code}")

    soup = BeautifulSoup(r.content, 'html.parser')
    items = soup.find_all('a', {'class': 'image'})
    for item in items:
        item_url = item['href']
        if 'cdn.bunkr.is' in item_url:
            item_url = item_url.replace('cdn.bunkr.is', 'media-files.bunkr.is')
        extension = get_extension_from_url(item_url)
        if extension in extensions_list or len(extensions_list) == 0:
            print(f"[+] Downloading {item_url}")
            download(item_url)


def download(item_url):

    if not os.path.isdir('cyberdrop_downloads'):
        os.mkdir('cyberdrop_downloads')
    
    file_name = get_file_name_from_url(item_url)
    with open(os.path.join('cyberdrop_downloads', file_name), 'wb') as f:
        r = requests.get(item_url)
        f.write(r.content)

    return

def get_extension_from_url(url):
    path = urlparse(url).path
    ext = splitext(path)[1]
    return ext

def get_file_name_from_url(url):
    path = urlparse(url).path
    file_name = os.path.basename(path)
    return file_name

if __name__ == '__main__':

    parser = argparse.ArgumentParser(sys.argv[1:])
    parser.add_argument("-u", help="Url to fetch", type=str)
    parser.add_argument("-e", help="Extensions to download (comma separated)", type=str)

    args = parser.parse_args()

    if args.u is None or args.u == "":
        raise Exception("No url specified")

    get_items_list(args.u, args.e)
    
    