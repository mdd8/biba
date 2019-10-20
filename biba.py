#!/usr/bin/env python

import subprocess
import getopt
import mechanize
import re, os, sys
import sys, logging
import urllib.parse
from bs4 import BeautifulSoup
from glob import glob
import configparser
from pathlib import Path
import argparse

################################OPTIONS PROCESSING##########################

def langcheck(lang):
    choices =   ['Irish', 'German', 'French', 'Spanish',
                'Italian', 'Latin', 'Hebrew', 'Hindi', 'Japanese', 
                'Danish', 'Swedish', 'Norwegian', 'Finnish', 'Dutch',
                'Tamil', 'Inuktitut', 'Esperanto', 'Russian', 'English',       
                'Slovenian', 'Bengali', 'Arabic', 'Tagalog', 'Indonesian',
                'Thai', 'Chinese', 'Korean', 'Romanian', 'Ukrainian', 
                'Macedonian', 'Croatian', 'Serbian', 'Slovak', 'Czech',
                'Bulgarian', 'Hungarian', 'Turkish', 'Catalan', 'Greek', 
                'Portuguese', 'Polish']
    if lang not in choices:
        print(  'bibliotik supports following languages only:', choices)
        sys.exit()


parser = argparse.ArgumentParser(usage='%(prog)s FILE [options]', 
    description='decrypt aax files and upload them to bibliotik.',
    epilog='Emperor protects!', prog='biba') 
parser.add_argument('files', nargs='?', help='aax file(s) to process, supports wildcards(* and ?)', metavar="FILE")
parser.add_argument('--activation', '-a', dest='activation', help='audible activation bytes')
parser.add_argument('--tags', '-t', nargs='*', help='at least one of "fiction", "nonfiction" or "poetry" tags is required')
parser.add_argument('--lang', '-l', nargs='?', default='English', help='audiobook language')
parser.add_argument('--cleanup', '-c',  dest='cleanup', action='store_true', help='delete aax file(s) afterwards', default=False)
parser.add_argument('--noupload', '-n',  dest='no_upload', action='store_true', help='do not upload, decrypt only', default=False)
parser.add_argument('--m4a', '-m', dest='m4a_path', help='destination folder for m4a files')
parser.add_argument('--torrent', dest='torrent_path', default='torrents', help='torrent output folder')
parser.add_argument('--verbose', '-v', dest='verbose', action='store_true', help='verbose mode', default=False)
parser.add_argument('--info', '-i', action='store_true', help='only fetch and display book info', default=False)
group = parser.add_argument_group('torrent options')
group.add_argument('--anon', action='store_true', help='make the bibliotik torrent anonymous', default=False)
group.add_argument('--dont_notify', action='store_true', help='notify of new comments', default=False)
parser.add_argument('--version', action='version', version='0.1')

args = parser.parse_args()

config = configparser.ConfigParser()
config.read('biba.cfg')

if args.m4a_path:
    m4a_path = Path(args.m4a_path).expanduser().resolve()
    if not m4a_path.is_dir():
        print('--m4a must point to an existing folder') 
        sys.exit()

torrent_path = Path(args.torrent_path).expanduser().resolve()

if not torrent_path.is_dir():
    os.makedirs(torrent_path)

verbose = args.verbose

activation_bytes = args.activation

if not args.files:
    print('no files specified') 
    sys.exit() 

temp = glob(args.files)
files = []

for f in temp:
    if os.path.isfile(f) and os.path.splitext(f)[1] == '.aax': files.append(f)
     
if len(files) == 0:
    print('no aax files to process')
    sys.exit()
activation = config['settings']['activation']

if not activation_bytes and not activation:
    print('must provide audible activation bytes either in cfg or with --activation') 
    sys.exit()

if activation: activation_bytes = activation

username = config['settings']['username'].strip()
password = config['settings']['password'].strip()
qbpath = config['settings']['qbpath'].strip()

if not username or not password:
    print('can not proceed w/o bib credentials, edit the config file')

####################### RUNNING FFPROBE ##############################


for filename in files:

    cmd = 'ffprobe -activation_bytes ' + activation_bytes + ' ' + filename    
    output = subprocess.run(cmd, capture_output=True, text=True).stdout
    if not output:
        #often ffmpeg produces errors, we have to capture stderr instead
        output = subprocess.run(cmd, capture_output=True, text=True).stderr

############ EXTRACTING DATA FROM CURRENT AAX FILE ################
    result:dict = {}
    result.setdefault('tags', '')
    result['language'] = args.lang
    if args.tags: result['tags'] = args.tags
        
    for row in output.split('\n'):
        if '[aax] mismatch in checksums!' in row:
            print('error decoding aax, check activation bytes')
            sys.exit()
        
        if 'Error setting option activation_bytes to value' in row:
            print('could not set activation bytes, invalid argument')
            sys.exit()           

        if 'title           : ' in row:
            title = row.replace('title           : ', '').lstrip()
            result['title'] = title
            continue
        if 'artist          :' in row:
            artists = row.replace('artist          :', '').lstrip()
            result['authors'] = artists
            continue
        if 'copyright       :' in row:
            publisher = row.replace('date            :', '').lstrip()
            start_slice = publisher.find('(P)')
            start_slice = publisher.find(' ', start_slice)
            result['publisher'] = publisher[start_slice:].strip()
            result['publisher'] = re.sub('[^a-zA-Z0-9_ ]','', result['publisher'])
            continue
        if 'date            :' in row:
            date = row.replace('date            :', '').lstrip()
            result['year'] = date
            continue
        if 'Duration:' in row and 'start:' in row and 'bitrate:' in row:
            for data in row.split(','):
                if 'Duration:' in data:
                    duration = data.replace('Duration: ', '').lstrip()
                    var = duration.split(':')
                    duration = var[0] + ':' + var[1]
                    result['duration'] = duration
                    continue
                if 'bitrate:' in data:
                    bitrate = data.replace('bitrate: ', '').lstrip()
                    bitrate = bitrate.split()
                    bitrate = int(bitrate[0])
                    bitrate_list = [32, 64, 128, 192]
                    bitrate = min(bitrate_list, key=lambda x:abs(x-bitrate))
                    result['bitrate'] = str(bitrate)
                    
            break

    while not args.info and 'fiction' not in result['tags'] and 'nonfiction' not in result['tags'] and 'poetry' not in result['tags']:        
        print('\n***each book must have at least one of the following tags: fiction, nonfiction, poetry***\n')
        print('current book:', result['title'], '\n')
        print('use commas to separate tags \n')
        x = input('Enter tags:').lower()
        result['tags'] = [s.strip() for s in x.split(',')]

    result['tags'] = ', '.join(result['tags'])

########################### DECRYPTING AAX ############################
    if not args.info:
        print('decrypting', filename)
        print('might take some time, use verbose mode for details')
        path = Path(filename).parent.expanduser().resolve()
        if args.m4a_path: 
            path = Path(args.m4a_path).expanduser().resolve() 
        newname = Path(filename).name
        filename_m4a = os.path.splitext(newname)[0] + '.m4a'
        output_name = path.joinpath(filename_m4a)
        filename_aax = str(Path(filename).expanduser().resolve())
        cmd =   ('ffmpeg -y -activation_bytes ' + activation_bytes +
                ' -i ' + filename_aax + ' -c:a copy -vn ' + str(output_name))
        if verbose == True:
            output = subprocess.run(cmd)
        else:
            output = subprocess.run(cmd, capture_output=True, text=True)
        print('decrypted to', path)


        if args.no_upload:
            print('not uploading, finished processing', result['title'])
            continue
#####################FETCHING DATA FROM AUDIBLE########################

    if verbose == True:
        logger = logging.getLogger("mechanize")
        logger.addHandler(logging.StreamHandler(sys.stdout))
        logger.setLevel(logging.WARNING)


    br = mechanize.Browser()
    br.addheaders = [('User-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)\
                     AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.93\
                     Safari/537.36 Vivaldi/2.8.1664.40')]
    br.set_handle_robots(False)

    if verbose == True:
        br.set_debug_http(True)
        br.set_debug_responses(True)

    parsed_title = urllib.parse.quote(result['title'])
    parsed_author = urllib.parse.quote(result['authors'])

    print('looking up the book on audible..')
    url =   'https://www.audible.com/search?title={}&author_author={}'.format(parsed_title, parsed_author)
    

    br.open(url)

    for link in br.links():
        if '-Audiobook/' in link.url:
            print('found a match!')
            final_link = link.url
            break

    print('fetching book details..')
    page = br.open('https://www.audible.com' + final_link)
    html = page.read()
    
    soup = BeautifulSoup(html, 'html.parser')

    narrators = soup.find(class_ = 'narratorLabel').text
    title = soup.find('h1', class_ = 'bc-heading').text

    if soup.find('a', href=re.compile('search\?searchProvider')):
        t = soup.find('a', href=re.compile('search\?searchProvider'))
        publisher = t.string.strip()
        print(publisher)
        print('publisher:', publisher)
        result['publisher'] = publisher

    series = soup.find(class_ = 'seriesLabel')
    if series:
        series = series.text
        series = series.replace('Series:', '')
        series = series.strip()
        title = title + ' (' + series + ')'
        print('part of series, full title:', title)
        result['title'] = title
	


    narrators = narrators.replace('Narrated by:', '')
    narrators = [name.strip() for name in narrators.split(",")]
    result['narrators'] = ', '.join(narrators)

    description = soup.find(class_ = 'productPublisherSummary')
    description_soup = BeautifulSoup(str(description), 'html.parser')

    desc:str = '' 
    for p in description_soup.find_all('p'):
        text:str = ''
        for t in p.stripped_strings:
            text += ' ' + t
            text = text.replace('\n', ' ')
            text = text.strip()
        
        desc += text + '\n\n'     

    result['description'] = desc


    img_set = soup('img')
    for img in img_set:
        if 'SL500' in img['src']: 
            result['cover'] = img['src']
            break
    print('done fetching')

    if args.info:
        print('book details:', result)
        continue

######################## BIBLIOTIK ##################################

    params = {'username': username, 'password': password, 'returnto': '/upload/audiobooks'}
    request = mechanize.Request('https://bibliotik.me/upload/audiobooks',
        data=params)

    print('\nlogging in to bibliotik')
    try:
        response = br.open(request)
    except mechanize.HTTPError:
        print('wrong bibliotik username/password')
        sys.exit()

#############################CREATING TORRENT##########################

    html = response.read()
    soup = BeautifulSoup(html, 'html.parser')
    passkey = soup.find(size="90").get('value')
    print('found the passkey')
    filename = Path(filename).name
    torrent_name = os.path.splitext(filename)[0] + '.torrent'
    full_torrent = Path(torrent_path).joinpath(torrent_name)
    
    if  os.path.isfile(full_torrent):
        os.remove(full_torrent)
    #print('mktorrent params:', passkey, filename_m4a, torrent_name, output_name)    
    cmd = 'mktorrent -p -a "{}" -c "Emperor protects!" -n "{}" -o "{}" "{}"'.format(passkey, filename_m4a, torrent_name, output_name)
    #print(cmd)    

    print('creating torrent:', torrent_name)
    
    if args.verbose:
        output = subprocess.run(cmd)
    else:
        output = subprocess.run(cmd, capture_output=True, text=True).stderr
        
    
    

    full_torrent = Path(torrent_path).joinpath(torrent_name)
    os.rename(Path.cwd().joinpath( torrent_name), full_torrent)
    print('moving .torrent to', str(torrent_path))
################################UPLOADING###############################

    br.form = list(br.forms())[2]
    print('\nfilling in the details')
    torrent = open(full_torrent, mode='rb')

    br.form.add_file(torrent, filename=torrent_name)
    br.form['YearField'] = result['year']
    br.form['TitleField'] = result['title']
    br.form['AuthorsField'] = result['authors']
    br.form['NarratorsField'] = result['narrators']
    br.form['PublishersField'] = result['publisher']
    br.form['DurationField'] = result['duration']

    for item in br.form.find_control('FormatField').items:
        if 'm4a' in item.attrs['contents'].lower():
            item.selected = True
            break

    for item in br.form.find_control("BitrateField").items:
        if result['bitrate'] in item.attrs['contents']:
            item.selected = True
            break

    for item in br.form.find_control("LanguageField").items:
        if result['language'].lower() in item.attrs['contents'].lower():
            item.selected = True
            break

    br.form['TagsField'] = result['tags']
    br.form['ImageField'] = result['cover']
    br.form['DescriptionField'] = result['description']

    if args.dont_notify: br.find_control('NotifyField').items[0].selected = False
    if args.anon: br.find_control('AnonymousField').items[0].selected = True

    uploaded = br.submit()
    html = uploaded.read()
    soup = BeautifulSoup(html, 'html.parser')
    if soup.find('ul', id='formerrorlist'):
        errorlist = soup.find('ul', id='formerrorlist')
        soup = BeautifulSoup(str(errorlist), 'html.parser')
        tags = soup.find_all('li')
        print('torrent upload failed for the following reason(s):')
        print('\n**************************************************')
        for tag in tags:        
            print(tag.text)
        print('**************************************************')
        sys.exit()
    else:
        if args.cleanup:
            os.remove(filename_aax)
            print('cleaning up, removing .aax')
        if uploaded.code == 200:
            print('uploaded', result['title'])
            print('========================\n\n')



    

########################ADDING TO QB##############################################
    if qbpath:
        pattern = '\'|\"'
        qbpath = re.sub(pattern, '', qbpath)

        cmd = qbpath + ' --save-path={} --skip-hash-check \
                --skip-dialog=true --category=audiobook \
                {}'.format(path, full_torrent)
        output = subprocess.run(cmd, capture_output=True, text=True).stderr

