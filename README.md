# CyberdropBunkrDownloader

[![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/PaaaulZ/CyberdropBunkrDownloader?style=flat)](https://github.com/PaaaulZ/CyberdropBunkrDownloader/stargazers)
[![GitHub last commit](https://img.shields.io/github/last-commit/PaaaulZ/CyberdropBunkrDownloader?style=flat)](https://github.com/PaaaulZ/CyberdropBunkrDownloader/commits/main)


A lightweight Python downloader for Cyberdrop and Bunkr albums and files, supporting batch URLs, retries, file filtering, custom output directories and date-based filtering.

## Installation

1) Install Python 3.x
2) Clone or download this repository
3) Install requirements with ```python -m pip install -r requirements.txt```

## Supported services

- Cyberdrop
- Bunkr
- Filester

Both single album URLs and lists of URLs are supported.

## Usage

Basic usage: ```python dump.py -u <url>```

## Full usage

```

usage: dump.py ['--help'] [-h] [-u U] [-f F] [-r R] [-e E] [-p P] [-w] [--before BEFORE] [--after AFTER]

options:
  -h, --help       show this help message and exit
  -u U             Url to fetch
  -f F             File containing list of URLs to download
  -r R             Number of retries in case the connection fails
  -e E             Extensions to download (comma separated)
  -p P             Path to custom downloads folder
  -w               Export url list (ex: for wget)
  --before BEFORE  Export only files before this date (format yyyy-mm-ddThh:mm:ss es: 2025-01-02T00:01:02)
  --after AFTER    Export only files after this date (format yyyy-mm-ddThh:mm:ss es: 2025-01-02T00:01:02)
  ```

## Disclaimer

This tool is intended for downloading content that you have the right to access and download.

The author is not responsible for how this software is used.
