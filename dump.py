from distutils import extension
import requests
from bs4 import BeautifulSoup
import argparse
import sys
import os
from os.path import splitext
from urllib.parse import urlparse 
import json


def get_items_list(url, extensions):

    extensions_list = []
    if extensions is not None and extensions != "":
        extensions_list = extensions.split(',')

    r = requests.get(url)
    if r.status_code != 200:
        raise Exception(f"HTTP error {r.status_code}")

    soup = BeautifulSoup(r.content, 'html.parser')
    if "bunkr.is" in url:
        json_data_element = soup.find("script", {"id": "__NEXT_DATA__"})
        json_data = json.loads(json_data_element.string)
        files = json_data["props"]["pageProps"]["files"]
        item_urls = [
            "https://media-files.bunkr.is/" + file["name"]
            for file in files
        ]
    else:
        items = soup.find_all('a', {'class': 'image'})
        item_urls = [item['href'] for item in items]

    for item_url in item_urls:
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
    
    
