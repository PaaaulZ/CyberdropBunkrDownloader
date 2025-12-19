# CyberdropBunkrDownloader
Simple downloader for cyberdrop.me and bunkr.ru


# Usage

Before using install requirements with ```pip3 install -r requirements.txt```

Basic usage: ```python3 dump.py -u [url]```

File usage: ```python3 dump.py -f list.txt```

# Full usage

```
usage: ['--help'] [-h] [-u U | -f F] [-r R] [-e E] [-s [S]] [-i] [-p P] [-w] [-cfs] [-css]

optional arguments:
  -h, --help  show this help message and exit
  -u U        Url to fetch
  -f F        File of Urls to fetch
  -r R        Amount of retries in case the connection fails
  -e E        Extensions to download (comma separated)
  -p P        Path to custom downloads folder
  -w          Export url list (ex: for wget)
  -css        Check server status before downloading
  --before    Export only files before this date (format yyyy-mm-ddThh:mm:ss es: 2025-01-02T00:01:02)
  --after     Export only files after this date (format yyyy-mm-ddThh:mm:ss es: 2025-01-02T00:01:02)
  ```
