import requests
import json
from bs4 import BeautifulSoup

def download():

    print("[?] Requesting album list")
    r = requests.get('https://bunkr.ru/albums', headers={'User-Agent': 'Mozilla/5.0'})
    if r.status_code != 200:
        raise Exception(f"\t[-] HTTP Error {r.status_code}")

    soup = BeautifulSoup(r.content, 'html.parser')
    json_data_element_text = soup.find("script", {"id": "__NEXT_DATA__"}).string
    json_data = json.loads(json_data_element_text)
    print("\t[+] Writing to albums.json")
    with open('albums.json', 'w') as f:
        json.dump(json_data, f)

    albums = json_data['props']['pageProps']['albums']
    
    print("\t[+] Writing to albums.csv")
    f = open('albums.csv', 'w')
    f.write("Album Name;URL\n")
    for album in albums:
        f.write(f"{album['name'].replace(';',' ')};https://bunkr.ru/a/{album['identifier']}\n")
    f.close()

    print("\t[+] Done")

    return

if __name__ == '__main__':
    download()