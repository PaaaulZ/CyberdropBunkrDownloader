# CyberdropBunkrDownloader
Simple downloader for cyberdrop.me and bunkr.is


# Usage

Before using install requirements with

```
pip3 install -r requirements.txt
```

```
python3 dump.py -u [url]
```

Download only specific extensions (optional):

```
python3 dump.py -u [url] -e [extensions (comma separated)] ex: python3 dump.py -u [url] -e [.jpg,.mp4]
```

Download only files bigger than specified size (optional, only for Bunkr):

```
python3 dump.py -u [url] -e [extensions (comma separated)] ex: python3 dump.py -u [url] -s [size in kylobytes]
```

Use album id for folder name instead of album name (optional, only for Bunkr):

```
python3 dump.py -u [url] -e [extensions (comma separated)] ex: python3 dump.py -u [url] -i 
```

Choose a custom download path

```
python3 dump.py -u [url] -p [path to download folder] ex: python3 dump.py -u [url] -p "E:\download_folder" or python3 dump.py -u [url] -p "/home/test/download_folder"
```