# -*- coding: utf-8 -*-

"""
MIT License

Original work Copyright (c) 2016 Vit Baisa
Modified work Copyright (c) 2017 Lukáš Geľo

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import os
import sys
import argparse
import urllib
import time
import datetime
import gzip
from justext import core as justext
import json
from bs4 import BeautifulSoup

LATEST = 'https://dumps.wikimedia.org/%swikivoyage/latest/%swikivoyage-latest-all-titles-in-ns0.gz'
API_HTML = 'https://%s.wikivoyage.org/w/api.php?action=parse&page=%s&format=json'

last_api_request = datetime.datetime.now()

class MissingPage(Exception):
    pass

class EmptyHTML(Exception):
    pass

class EmptyJusText(Exception):
    pass

def api_wait(last):
    global wait_interval
    n = datetime.datetime.now()
    interval = (n-last).seconds + ((n-last).microseconds / 1.0e6)
    if interval < wait_interval:
        time.sleep(wait_interval - interval)

def line_count(fname):
    with gzip.open(fname) as f:
        for i, l in enumerate(f):
            pass
    return i + 1

def display_processed(current, all_articles):
    sys.stdout.write('\r')
    sys.stdout.write('Processed article: %d/%d ' % (current, all_articles))
    sys.stdout.flush()

def getPageText(title, langcode, stoplist, logf):
    global last_api_request
    api_wait(last_api_request)
    last_api_request = datetime.datetime.now()
    resp = urllib.urlopen(API_HTML % (langcode, title))
    data = json.load(resp)
    if 'error' in data:
        print >>logf, '\tmissing page'
        raise MissingPage()
    p = data['parse']
    html = p['text']['*']
    if not html.strip():
        print >>logf, '\tempty HTML parse returned by API'
        raise EmptyHTML()

    soup = BeautifulSoup(html, 'lxml')
    [x.extract() for x in soup.findAll('div', 'toc')]# table of content
    [x.extract() for x in soup.findAll('ol', 'references')]
    [x.extract() for x in soup.findAll('div', 'navbox')]
    [x.extract() for x in soup.findAll('pre')]
    """[x.extract() for x in soup.findAll('table', 'notice noprint notice-todo')]
    [x.extract() for x in soup.findAll('table', 'plainlinks cmbox cmbox-content')]
    [x.extract() for x in soup.findAll('table', 'plainlinks tmbox tmbox-notice')]
    [x.extract() for x in soup.findAll('table', 'metadata plainlinks ambox ambox-speedy')]
    [x.extract() for x in soup.findAll('table', 'plainlinks cmbox cmbox-speedy')]
    [x.extract() for x in soup.findAll('table', 'metadata plainlinks ambox ambox-delete')]
    [x.extract() for x in soup.findAll('table', 'plainlinks noprint xambox xambox-type-notice')]
    [x.extract() for x in soup.findAll('table', 'plainlinks xambox xambox-type-notice')]
    [x.extract() for x in soup.findAll('table', 'plainlinks xambox xambox-type-content')]
    [x.extract() for x in soup.findAll('div', 'label_message')]
    [x.extract() for x in soup.findAll('div', 'boilerplate metadata')]
    [x.extract() for x in soup.findAll('div', 'noprint request box')]
    [x.extract() for x in soup.findAll('td', 'mbox-text')]"""

    [x.extract() for x in soup.findAll('a', 'mw-kartographer-maplink mw-kartographer-autostyled')]
    [x.extract() for x in soup.findAll('abbr', 'phone')]
    """[x.extract() for x in soup.findAll('span', 'listing-metadata')]"""

    if stoplist == 'None': #with stopwords_high = 0, stopwords_low = 0 language is ignored
        paragraphs = justext.justext(soup.encode('utf-8'), justext.get_stoplist('English'), stopwords_high = 0, stopwords_low = 0, no_headings=True)
    else:
        paragraphs = justext.justext(soup.encode('utf-8'), justext.get_stoplist(stoplist), no_headings=True)
    text = ''
    parSum = 0
    charSum = 0
    wordSum = 0
    for paragraph in paragraphs:
        if paragraph['class'] == 'good' and paragraph['cfclass'] != 'short':
            line = paragraph.get('text')
            text += '<p>\n'
            text += line
            text += '\n</p>\n'
            parSum += 1
            wordSum += paragraph['word_count']
            charSum += len(line)
    if (parSum == 0):
        print >>logf, '\tempty prevert returned by jusText'
        raise EmptyJusText()
    print >>logf, '\t%d words' % wordSum
    print >>logf, '\t%d paragraphs' % parSum
    categories = ';'.join([d['*'].replace('"', '') for d in p['categories']])
    header = '<doc title="%s" categories="%s" translations="%d" paragraphs="%d" words="%d" chars="%d">\n' %\
            (title.decode('utf-8'), categories, len(p['langlinks']), parSum, wordSum, charSum)
    return header + text + '</doc>\n'

def main(langcode, stoplist):
    outputfn = 'wikivoyage_%s.prevert' % langcode
    current_time = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    logfn = 'wikivoyage_%s_' % langcode + current_time + '.log'
    cachefn = 'wikivoyage_%s.cache' % langcode
    with open(logfn, 'w') as logf:
        cache = []
        if os.path.exists(cachefn):
            print >>logf, 'Cache: %s' % cachefn
            with open(cachefn) as cf:
                for line in cf:
                    cache.append(line.strip())
        with open(cachefn, 'a') as cf:
            with open(outputfn, 'ab') as preverttext:
                filename, _ = urllib.urlretrieve(LATEST % (langcode, langcode))
                all_articles = line_count(filename)
                empty_articles = 0
                skipped_articles = 0
                with gzip.open(filename) as df:
                    i = 0 #number of currently processed article
                    for line in df:
                        title = line.strip().replace('"', "'")
                        i += 1
                        print >>logf, '%s' % title
                        display_processed(i, all_articles)
                        if title in cache:
                            print >>logf, '\tskip already downloaded'
                            skipped_articles += 1
                            pagetext = ''
                        else:
                            try:
                                pagetext = getPageText(title, langcode, stoplist, logf)
                                cf.write(title + '\n')
                            except(MissingPage, EmptyHTML, EmptyJusText):
                                pagetext = ''
                                empty_articles += 1
                                cf.write(title + '\n')
                            except ValueError as e:
                                print >>logf, '\tValueError: %s' % e
                                pagetext = ''
                                empty_articles += 1
                            except IOError as e:
                                print >>logf, '\tIOError: %s' % e
                                pagetext = ''
                                empty_articles += 1
                            except:
                                print >>logf, '\tUnexpected error.'
                                raise
                            preverttext.write(bytes(pagetext.encode('utf-8')))
                    sys.stdout.write('Finished\n')

            print >>logf, 'Processed: %d' % (i - empty_articles - skipped_articles)
            print >>logf, 'Empty: %d' % empty_articles
            print >>logf, 'Skipped: %d' % skipped_articles

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Wikivoyage downloader')
    parser.add_argument('langcode', type=str, help='Wikivoyage language prefix, e.g. en')
    parser.add_argument('-s', '--stoplist', type=str, help='stoplist name/name of language (default None), e.g. English', default='None')
    args = parser.parse_args()
    wait_interval = 0.2
    main(args.langcode, args.stoplist)
