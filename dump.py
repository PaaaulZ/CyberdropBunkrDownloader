#!/usr/bin/env python3
import time
import requests
import json
import argparse
import sys
import os
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from tqdm import tqdm


def get_items_list(session, url, retries, extensions, only_export, custom_path=None):
    extensions_list = extensions.split(',') if extensions is not None else []

    r = session.get(url)
    if r.status_code != 200:
        raise Exception(f"[-] HTTP error {r.status_code}")

    soup = BeautifulSoup(r.content, 'html.parser')
    is_bunkr = "Bunkr" in soup.find('title').text if soup.find('title') else False

    direct_link = False

    if is_bunkr:
        items = []
        soup = BeautifulSoup(r.content, 'html.parser')

        # Check if this is a direct link page
        direct_link = soup.find('span', {'class': 'ic-videos'}) is not None or soup.find('div', {'class': 'lightgallery'}) is not None
        if direct_link:
            album_name = soup.find('h1', {'class': 'text-[20px]'})
            if album_name is None:
                album_name = soup.find('h1', {'class': 'truncate'})
            album_name = remove_illegal_chars(album_name.text if album_name else "Unknown")
            items.append(get_real_download_url(session, url, True))
        else:
            # Process album page: get all file items
            boxes = soup.find_all('a', {'class': 'after:absolute'})
            for box in boxes:
                href = box.get('href')
                if href:
                    items.append({'url': href, 'size': -1})
            album_name = soup.find('h1', {'class': 'truncate'})
            album_name = remove_illegal_chars(album_name.text if album_name else "Unknown")
    else:
        items = []
        items_dom = soup.find_all('a', {'class': 'image'})
        for item_dom in items_dom:
            items.append({'url': f"https://cyberdrop.me{item_dom['href']}", 'size': -1})
        album_name = remove_illegal_chars(soup.find('h1', {'id': 'title'}).text if soup.find('h1', {'id': 'title'}) else "Unknown")

    download_path = get_and_prepare_download_path(custom_path, album_name)
    already_downloaded_url = get_already_downloaded_url(download_path)

    for item in items:
        if not direct_link:
            print(f"\t[DEBUG] Processing item: {item}")
            item = get_real_download_url(session, item['url'], is_bunkr)
            if item is None or 'url' not in item or not item['url']:
                print(f"\t\t[-] Unable to find a valid download link for {item.get('url', 'unknown URL')}")
                continue

        if not item['url'] or item['url'] == '#':
            print(f"\t\t[-] Invalid URL '{item['url']}' found. Skipping.")
            continue

        extension = get_url_data(item['url'])['extension']
        if ((extension in extensions_list or len(extensions_list) == 0) and (item['url'] not in already_downloaded_url)):
            if only_export:
                write_url_to_list(item['url'], download_path)
            else:
                for i in range(1, retries + 1):
                    try:
                        print(f"\t[+] Downloading {item['url']} (try {i}/{retries})")
                        download(session, item['url'], download_path, is_bunkr, item.get('name'))
                        break
                    except requests.exceptions.ConnectionError as e:
                        if i < retries:
                            time.sleep(2)
                        else:
                            raise e
                    except requests.exceptions.MissingSchema as e:
                        print(f"\t\t[-] Invalid URL: {item['url']}")
                        break

    if only_export:
        print(f"\t[+] File list exported in {os.path.join(download_path, 'url_list.txt')}")
    else:
        print(f"\t[+] Download completed")
    return


def get_real_download_url(session, url, is_bunkr=True):
    if is_bunkr:
        if not url.startswith('http'):
            url = urljoin('https://bunkr.sk', url)
    else:
        url = url.replace('/f/','/api/f/')

    print(f"\t[DEBUG] Fetching real download URL for: {url}")

    try:
        r = session.get(url)
        if r.status_code != 200:
            print(f"\t[-] HTTP error {r.status_code} getting real url for {url}")
            return {'url': None, 'size': -1}

        if is_bunkr:
            soup = BeautifulSoup(r.content, 'html.parser')
            title = soup.find('title')
            file_name = title.text.split(' | ')[0].strip() if title else None
            print(f"\t[DEBUG] File name from title: {file_name}")
            print(f"\t[DEBUG] File page HTML: {r.text[:500]}...")

            # Attempt to find the download button that goes to the get.bunkrr.su page
            download_btn = soup.find('a', {'class': 'ic-download-01'})
            if download_btn and download_btn.get('href'):
                # Try to extract a direct CDN URL based on file id format if present
                file_id_match = re.search(r'file/(\d+)', download_btn['href'])
                if file_id_match:
                    file_id = file_id_match.group(1)
                    direct_cdn_url = f"https://media-files2.bunkr.ru/{file_id}"
                    print(f"\t[DEBUG] Trying direct CDN URL: {direct_cdn_url}")
                    return {'url': direct_cdn_url, 'size': -1, 'name': file_name}
                # Otherwise, try to get the final download link from the download page
                download_url = get_cdn_file_url(session, download_btn['href'])
                if download_url:
                    return {'url': download_url, 'size': -1, 'name': file_name}

            # Fallback: check for video or image elements
            video_player = soup.find('video', {'id': 'player'})
            source_dom = soup.find('source')
            media_player_dom = soup.find('media-player')
            image_dom = soup.find('img', {'class': 'max-h-full'})
            if source_dom and source_dom.get('src'):
                return {'url': source_dom['src'], 'size': -1, 'name': file_name}
            if media_player_dom and media_player_dom.get('src'):
                return {'url': media_player_dom['src'], 'size': -1, 'name': file_name}
            if video_player and video_player.get('src'):
                return {'url': video_player['src'], 'size': -1, 'name': file_name}
            if image_dom and image_dom.get('src'):
                return {'url': image_dom['src'], 'size': -1, 'name': file_name}

            # Alternative debug approach using potential debug info in the page
            debug_info = re.search(r'Debug: Original=([^,]+), Size=(\d+)', r.text)
            if debug_info:
                file_name = debug_info.group(1)
                size = int(debug_info.group(2))
                file_id_match = re.search(r'/f/([a-zA-Z0-9]+)', url)
                if file_id_match:
                    file_id = file_id_match.group(1)
                    direct_cdn_url = f"https://media-files.bunkr.ru/{file_id}/{file_name}"
                    print(f"\t[DEBUG] Trying alternative direct CDN URL: {direct_cdn_url}")
                    return {'url': direct_cdn_url, 'size': size, 'name': file_name}

            print(f"\t[-] Unable to find a valid download URL for {url}")
            return {'url': None, 'size': -1}
        else:
            try:
                item_data = json.loads(r.content)
                if 'url' in item_data:
                    return {'url': item_data['url'], 'size': -1, 'name': item_data.get('name', '')}
                else:
                    print(f"\t[-] No 'url' field found in the JSON response for {url}")
                    return {'url': None, 'size': -1}
            except json.JSONDecodeError:
                print(f"\t[-] Failed to parse JSON response for {url}")
                return {'url': None, 'size': -1}

    except Exception as e:
        print(f"\t[-] Error while getting real download URL: {str(e)}")
        return {'url': None, 'size': -1}


def get_cdn_file_url(session, download_page_url):
    if not download_page_url.startswith('http'):
        download_page_url = urljoin('https://bunkr.sk', download_page_url)

    print(f"\t[DEBUG] Getting CDN URL from: {download_page_url}")

    try:
        r = session.get(download_page_url)
        if r.status_code != 200:
            print(f"\t\t[-] HTTP ERROR {r.status_code} getting direct CDN url")
            return None

        # For debugging: print part of the HTML content
        print(f"\t[DEBUG] Download page HTML: {r.text[:500]}...")

        soup = BeautifulSoup(r.content, 'html.parser')

        # First try: search all <a> tags with the text exactly "Download"
        for a_tag in soup.find_all('a'):
            if a_tag.string and a_tag.string.strip() == 'Download':
                href = a_tag.get('href')
                if href and href != '#':
                    return href

        # Second try: case-insensitive search for "download" in the text
        for a_tag in soup.find_all('a'):
            if a_tag.string and 'download' in a_tag.string.lower().strip():
                href = a_tag.get('href')
                if href and href != '#':
                    return href

        # Third try: use CSS selectors for any href starting with http
        download_links = soup.select('a[href^="http"]')
        if download_links:
            for link in download_links:
                candidate = link.get('href')
                if candidate and ('bunkr' not in candidate.lower()):
                    return candidate

        # Fourth try: regex extraction from raw HTML for common extensions
        cdn_urls = re.findall(r'href=[\'"]([^\'"]+\.(?:mp4|jpg|jpeg|png|gif|webm))[\'"]', r.text)
        if cdn_urls:
            return cdn_urls[0]

        # Fifth try: scan the lines for a download link
        lines = r.text.split("\n")
        for line in lines:
            if 'Download' in line and 'href=' in line:
                match = re.search(r'href=[\'"]([^\'"]+)[\'"]', line)
                if match:
                    candidate = match.group(1)
                    if candidate and candidate != '#':
                        return candidate

        # Sixth try: if file size is shown, get the next link
        file_size_pattern = re.compile(r'\d+\.\d+\s*[MG]B')
        for element in soup.find_all(text=file_size_pattern):
            next_element = element.find_next('a')
            if next_element and next_element.get('href'):
                candidate = next_element.get('href')
                if candidate and candidate != '#':
                    return candidate

        # Last resort: scan the entire text for any URL that likely is a CDN URL
        all_urls = re.findall(r'(https?://[^\s"\'<>]+)', r.text)
        for url in all_urls:
            if ('cdn' in url.lower() or any(ext in url.lower() for ext in ['.mp4', '.jpg', '.jpeg', '.png', '.gif', '.webm'])):
                return url

        print(f"\t\t[-] No download link found on page {download_page_url}")
        return None

    except Exception as e:
        print(f"\t\t[-] Error getting CDN URL: {str(e)}")
        return None


def download(session, item_url, download_path, is_bunkr=False, file_name=None):
    if not item_url:
        print("\t[-] Invalid URL for download")
        return

    url_data = get_url_data(item_url)
    if not file_name:
        file_name = url_data['file_name']

    if not os.path.splitext(file_name)[1] and url_data['extension']:
        file_name = f"{file_name}{url_data['extension']}"

    final_path = os.path.join(download_path, file_name)

    try:
        with session.get(item_url, stream=True, timeout=10) as r:
            if r.status_code != 200:
                print(f"\t[-] Error downloading \"{file_name}\": {r.status_code}")
                return
            if r.url == "https://bnkr.b-cdn.net/maintenance.mp4":
                print(f"\t[-] Error downloading \"{file_name}\": Server is down for maintenance")
                return

            file_size = int(r.headers.get('content-length', -1))
            with open(final_path, 'wb') as f:
                with tqdm(total=file_size, unit='iB', unit_scale=True, desc=file_name, leave=False) as pbar:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))

        if is_bunkr and file_size > 0:
            downloaded_file_size = os.stat(final_path).st_size
            if downloaded_file_size != file_size:
                print(f"\t[-] {file_name} size check failed, file could be broken\n")
                return

        mark_as_downloaded(item_url, download_path)
        print(f"\t[+] Successfully downloaded: {file_name}")

    except Exception as e:
        print(f"\t[-] Error during download of {file_name}: {str(e)}")


def create_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
        'Referer': 'https://bunkr.sk/',
    })
    return session


def get_url_data(url):
    parsed_url = urlparse(url)
    file_name = os.path.basename(parsed_url.path)
    extension = os.path.splitext(parsed_url.path)[1]
    return {'file_name': file_name, 'extension': extension, 'hostname': parsed_url.hostname}


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


def remove_illegal_chars(string):
    illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in illegal_chars:
        string = string.replace(char, '')
    return string.strip()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CyberdropBunkrDownloader')
    parser.add_argument('-u', metavar='URL', type=str, help='URL to download from')
    parser.add_argument('-f', metavar='FILE', type=str, help='File containing URLs to download')
    parser.add_argument('-r', metavar='RETRIES', type=int, default=10, help='Number of retries for failed downloads')
    parser.add_argument('-e', metavar='EXTENSIONS', type=str, help='Comma-separated list of file extensions to download (e.g. "jpg,png,gif")')
    parser.add_argument('-w', action='store_true', help='Write URLs to a file instead of downloading')
    parser.add_argument('-p', metavar='PATH', type=str, help='Custom download path')

    args = parser.parse_args()

    if not args.u and not args.f:
        parser.print_help()
        sys.exit(1)

    session = create_session()

    if args.u:
        try:
            get_items_list(session, args.u, args.r, args.e, args.w, args.p)
        except KeyboardInterrupt:
            print("\n[!] Download interrupted by user")
            sys.exit(0)
        except Exception as e:
            print(f"[-] Error: {str(e)}")
            sys.exit(1)
    elif args.f:
        try:
            with open(args.f, 'r') as f:
                urls = f.readlines()
            for url in urls:
                url = url.strip()
                if url:
                    print(f"[+] Processing {url}")
                    try:
                        get_items_list(session, url, args.r, args.e, args.w, args.p)
                    except Exception as e:
                        print(f"[-] Error processing {url}: {str(e)}")
        except KeyboardInterrupt:
            print("\n[!] Download interrupted by user")
            sys.exit(0)
        except Exception as e:
            print(f"[-] Error: {str(e)}")
            sys.exit(1)