# biba
bibliotik aax audiobook uploader

1) ffmpeg installed and in your $PATH
2) mktorrent installed and in your $PATH
3) tested on python 3.7+
4) pip install mechanize bs4 configparser pathlib
5) you need your audible activation bytes, get them here: https://github.com/inAudible-NG/audible-activator
6) edit biba.cfg

some books have special store pages'(e.g. https://anonym.to/?https://www.audible.com/pd/Stan-Lees-Alliances-A-Trick-of-Light-Audiobook/B07Q41BM5D) layout and won't be fetched.

if you use qb you could configure auto torrent adding, look into biba.cfg

read help for full options breakdown: py biba.py -h
supports wildcards ? and *
