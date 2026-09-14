#!/bin/env python3

# Mystic Link Worldwide Web Crawler
# Web crawler
import configparser
import gc
import re
import requests
import sys
import csv
import urllib.parse
from bs4 import BeautifulSoup
from time import sleep
from settings import *
from scrape import scrapeDataFromPage
from store import storeDataFromPage

def cleanURL(url):
    nextURL = url.split('#')[0]
    r = urllib.parse.urlparse(nextURL)
    if r.scheme == '': 
        nextURL = "https://" + nextURL

    return nextURL
    
# Takes a string and a list of strings or regular expressions, and returns True if any of the list items are found in the string
def testFilter(url, filters=[]):
    for f in filters:
        if re.search(f, url) != None:
            #print(f"Match! {f} in {url}")
            return True
    return False

def getHTMLSoup(url, headers={'User-Agent': USER_AGENT}):
    print(url)
    r = requests.get(url, headers=headers)
    if r.status_code == requests.codes.ok:
        size = len(r.content)
        if size == 0: raise Exception("Page Empty")
        print(f"Size of page = {size}")
        return BeautifulSoup(r.content, features="lxml")
    else:
        r.raise_for_status()

# A web crawling job
#
# startURL (required)
# the URL to crawl first. The crawler will only follow links begining with this value for the rest of the job.
# For example, to crawl all of example.com, set to "https://www.example.com/"
# To crawl only the portion of the site begining with '/blog', set to "https://www.example.com/blog"
#
# crawlURLFilters (optional)
# A list of strings or regular expressions for choosing which URLs to follow. Default value is [''] meaning follow everything
#
# scrapeURLFilters (optional)
# A list of strings or regular expressions for choosing which webpages to scrape. Default value is [''] meaning scrape everything
# To scrape only webpages where the URL contains the word 'recipe' then set to 'recipe'
#
# dontCrawlURLFilters (optional)
# A list of strings or regular expressions to explicitly exclude URLs to follow. Default value is [] meaning don't exclude anything
#
# dontScrapeURLFilters (optional)
# A list of strings or regular expressions to explicitly exclude webpages to scrape. Default value is [] meaning don't exclude anything
class Job:
    # Initialization also starts the crawler at the startURL.
    # The following line will start crawling at https://example.com/blog/
    # newJob = Job("example.com/blog/")
    def __init__(self, startURL, crawlURLFilters=[''], scrapeURLFilters=[''], dontCrawlURLFilters=[], dontScrapeURLFilters=[]):
        self.startURL = cleanURL(startURL)
        print(self.startURL)
        self.crawlURLFilters = crawlURLFilters
        self.scrapeURLFilters = scrapeURLFilters
        self.dontCrawlURLFilters = dontCrawlURLFilters + GLOBAL_CRAWL_AVOID
        self.dontScrapeURLFilters = dontScrapeURLFilters + GLOBAL_STORE_AVOID
        self.requestDelay = REQUEST_DELAY
        self.visitedURLs = []
        self.queuedURLs = []
        self.totalScrapedPages = 0
        #self.paused = False

        self.crawl(self.startURL)

    def getPageLinks(self, url, htmlSoup):
        urls = []
        links = htmlSoup.find_all('a')
        for link in links:
            href = link.get('href')
            href = urllib.parse.urljoin(url, href)
            href = cleanURL(href)
            r = urllib.parse.urlparse(href)
            if all([r.scheme,
                    r.netloc,
                    (not href in self.queuedURLs),
                    (not href in self.visitedURLs)]):
                        urls.append(href)
                        self.queuedURLs.append(href)
                        #self.queuedURLs += 1
        return urls

    def crawl(self, url):
        #print(self.crawlURLFilters)
        #print(self.scrapeURLFilters)
        #print(self.dontCrawlURLFilters)
        #print(self.dontScrapeURLFilters)
        collected = gc.collect()
        #while self.paused:
        #    sleep(10)
        
        #if not url.startswith(self.startURL):
        #    print("Skipping " + url + " does not start with " + self.startURL)
        #    return
        try:
            self.queuedURLs.remove(url)
        except Exception:
            pass

        if url in self.visitedURLs:
            print("Skipping duplicate URL: " + url)
            return

        self.visitedURLs.append(url)

        if not testFilter(url, self.crawlURLFilters):
            print(f"Skipped Crawling filtered URL: {url}")
            return 
            
        if testFilter(url, self.dontCrawlURLFilters):
            print(f"Skipped Crawling explicitly filtered URL: {url}")
            return

        try:
            html = getHTMLSoup(url)
        except requests.HTTPError as e:
            code = e.response.status_code
            match code:
                case 429:
                    self.requestDelay += .04

            return
        except Exception as e:
            print(f"\033[91mError: {e}")
            print("URL = " + url + "\033[0m")
            return

        if (testFilter(url, self.scrapeURLFilters) and not testFilter(url, self.dontScrapeURLFilters)):
            print("\033[92mIndexing: " + url + "\033[0m")
            data = ()
            try:
                data = scrapeDataFromPage(html)
                self.totalScrapedPages += 1
            except NameError:
                print("\033[91mError: Could not index URL. The 'scrapeDataFromPage(html)' function has not been defined.")
                print("To remove this error, define a scrape function. See documentation for more info\033[0m")

            try:
                storeDataFromPage(data,url)
                #print("Success")
            except NameError:
                print("\033[91mError: Could not store webpage data. The 'storeDataFromPage(data, url)' function has not been defined.")
                print("To remove this error, define a store function. See documentation for more info\033[0m")
        pageLinks = self.getPageLinks(url, html)

        for link in pageLinks:
            self.crawl(link)
        print("Pages indexed: " + str(self.totalScrapedPages))
    #def pause(self):
    #    self.pause = True
    
    
class Batch:
    def __init__(self, batchFile):
        self.jobQueue = []
        self.config = configparser.ConfigParser()
        self.config.read(batchFile)

    def startBatch(self):
        # Read each line in the ini file
        for section in self.config.sections():
            line = {}
            for key in self.config[section]:
                line[key] = self.config[section][key]
            self.jobQueue.append(line)

        for j in self.jobQueue:
            collected = gc.collect()
            startURL = j["starturl"]
            crawlURLFilters=j["crawlurlfilters"].split(',')
            scrapeURLFilters=j["scrapeurlfilters"].split(',')
            dontCrawlURLFilters=j["dontcrawlurlfilters"].split(',')
            if dontCrawlURLFilters == ['']:
                dontCrawlURLFilters = []
            dontScrapeURLFilters=j["dontscrapeurlfilters"].split(',')
            if dontScrapeURLFilters == ['']:
                dontScrapeURLFilters = []
            print(startURL)
            print(crawlURLFilters)
            print(scrapeURLFilters)
            print(dontCrawlURLFilters)
            print(dontScrapeURLFilters)
            Job(startURL, crawlURLFilters, scrapeURLFilters, dontCrawlURLFilters, dontScrapeURLFilters)
            
print("Total arguments:", len(sys.argv))
print("Script name:", sys.argv[0])
print("Arguments:", sys.argv[1:])
if len(sys.argv) < 2:
    print("Usage: ", sys.argv[0], " [CSV Filename]")
    exit()
batchFile = sys.argv[1]
print("Batch file: ", batchFile)
if not batchFile.lower().endswith(".ini"):
    print(f"Error: {batchFile} not an ini file")
    exit()

B = Batch(batchFile)
B.startBatch()