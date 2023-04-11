#
# dl_playlists.py
#
# Download all of your Amazon music playlists to CSV files.
# 
# Requirements:
# - Mac (tested on Monterey 12.6.3)
# - Chrome
#  
# Outputs:
# - playlists.csv - All playlists
# - tracks.csv    - All tracks in all playlists
#

browserProfile='Default2'
accountName='account1'
getPlaylists = True
getPlaylistTracks = True
verbose = True

import os
import time
import math
import random
import re
import glob
import json
import csv

from contextlib import contextmanager

import urllib
import urllib.request
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager


def vprint(*msg):
    if verbose:
        print(*msg)

def fatalError(*msg):
    print(*msg)
    exit()

# wait a bit, to be nice to the site
def waitABit(baseSecs = 0.55):
   waitSecs = baseSecs + random.random() * (0.5 * baseSecs)
   vprint('        waiting ' + str(waitSecs) + ' secs')
   time.sleep(waitSecs)

# go down/up one dir level
def pushDir(dirName):
    if not os.path.exists(dirName):
       os.mkdir(dirName)
    os.chdir(dirName)

def popDir():
   os.chdir('..')

def jsonFileExists(basename):
    return os.path.exists(basename+'.json')

def writeToJsonFile(basename, strList):
    filename = basename+'.json'
    vprint('INFO: writing '+filename+'...\n', strList)
    with open(filename, 'w') as jsonFile:
        json.dump(strList, jsonFile, indent=4)

def readFromJsonFile(basename):
    filename = basename+'.json'
    vprint('INFO: reading '+filename+'...')
    strList = []
    with open(filename, 'r') as jsonFile:
        strList = json.load(jsonFile)
    return strList

def getWebPage(url, scrollToEndAndWait=False):
    vprint('INFO: getting page',url,'...')

    if not getWebPage.browserRunning:
        getWebPage.browserStartup()
    
    success = True
    html = ''
    try:
        getWebPage.browser.get(url)
        if scrollToEndAndWait:
            getWebPage.browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(5.14)
    except Exception as e:
        vprint('    ERROR: browser.get("%s,%s")'%url,e)
        success = False
        getWebPage.browserShutdown()

    if success:
        html = getWebPage.browser.page_source

    return BeautifulSoup(html, features="html.parser"), success

def browserStartup():
    options = webdriver.ChromeOptions()

    options.add_argument("--user-data-dir="+os.path.expanduser('~')+"/Library/Application Support/Google/Chrome/")
    options.add_argument('--browserProfile-directory='+'"'+browserProfile+'"') # reuse same profile so have login cookies
    options.add_experimental_option("excludeSwitches", ["test-type","enable-automation","enable-blink-features"]) # totally not automated
    options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2}) # no images: 0=default,1=allow,2=block

    getWebPage.browser = webdriver.Chrome(options=options, service=ChromeService(ChromeDriverManager().install()))
    vprint(getWebPage.browser.capabilities)
    getWebPage.browserRunning = True    

def browserShutdown():
    if getWebPage.browser != None:
        getWebPage.browser.quit()
        getWebPage.browser = None
        getWebPage.browserRunning = False

def addToURLList(urlList, url):
    if not url in urlList:
        urlList.append(url)
        vprint('ADDING',url)
        return True
    else:
        vprint('DUPLICATE',url)
        return False

@contextmanager
def ignore(*exceptions):
  try:
    yield
  except exceptions:
    pass 

def getAmazonPlaylists():
    rootUrl = 'https://music.amazon.com'

    # https://music.amazon.com/my/playlists/all
    # playlist name = <music-vertical-item primary-text="Music To Code To"
    if getPlaylists:
        url = rootUrl + '/my/playlists/all'

        playlistFields = ['playlistTitle','playlistUrl']
        with open('playlists.csv', 'w', newline='', encoding="utf-8") as playlistsFile:
            writer = csv.DictWriter(playlistsFile, playlistFields)
            writer.writeheader()
        playlistRows = []

        page, success = getWebPage(url, scrollToEndAndWait=True)
        if page != None and success:
            pageNum = 0
            while True:
                print('page',pageNum,'-----------------------------------------------')
                for tag in page.findAll('music-vertical-item'):
                    playlistUrl = tag.get('primary-href')
                    playlistTitle = tag.get('primary-text')
                    print (playlistTitle, playlistUrl)
                    playlistRow = {'playlistTitle':playlistTitle,'playlistUrl':playlistUrl}
                    if not playlistRow in playlistRows:
                        playlistRows.append(playlistRow)
                pageNum += 1

                lastHeight = getWebPage.browser.execute_script("return document.body.scrollHeight")
                getWebPage.browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(5)
                newHeight = getWebPage.browser.execute_script("return document.body.scrollHeight")
                if newHeight == lastHeight:
                    break
                html = getWebPage.browser.page_source
                page = BeautifulSoup(html, features="html.parser")

        with open('playlists.csv', 'a', newline='', encoding="utf-8") as playlistsFile:
            writer = csv.DictWriter(playlistsFile, playlistFields)
            writer.writerows(playlistRows)
    
    # https://music.amazon.com/my/playlists/xxxx-yyyy-zzzzz
    # track name = <a href="/albums/B001E40DVW?trackAsin=B001E45LJQ" rel="false">Ethnic Majority</a><div class="tags"><music-tag-group slot="tags" role="contentinfo" class="hydrated"></music-tag-group></div>
    # album name = <a href="/albums/B001E40DVW" rel="false">Carboot Soul</a><div class="tags"></div>
    # artist name = <a href="/artists/B000QJP7YY/nightmares-on-wax" rel="false">Nightmares On Wax</a><div class="tags"></div>
    # track length = (next div after album div) <div class="col4"><music-link class="hydrated" kind="secondary" role="link" title="06:20"><!-- --><span> 06:20 </span>
    if getPlaylistTracks:
        playlistRows = []
        with open('playlists.csv', 'r', newline='', encoding="utf-8") as playlistsFile:
            for row in csv.DictReader(playlistsFile, delimiter=','):
                playlistRows.append(row)

        trackFields = ['playlistUrl','playlistTitle','trackUrl','trackNum','trackName','trackLength','albumUrl','albumName','artistUrl','artistName']
        with open('tracks.csv', 'w', newline='', encoding="utf-8") as tracksFile:
            writer = csv.DictWriter(tracksFile, trackFields)
            writer.writeheader()

        # playlistRow = playlistRows[2] # TESTING 1
        # if True:                      # TESTING 1
        # for playlistNum in range (0,3):         # TESTING 2
        # playlistRow = playlistRows[playlistNum] # TESTING 2
        for playlistRow in playlistRows:
            print(playlistRow)
            playlistTitle = playlistRow['playlistTitle']
            playlistUrl = playlistRow['playlistUrl']
            url = rootUrl + playlistUrl
            page, success = getWebPage(url, scrollToEndAndWait=True)
            if page != None and success:
                pageNum = 0
                trackRows = []
                playlistTrackIds = []
                trackUrl = trackName = trackLength = albumUrl = albumName = artistUrl = artistName = ''
                trackNum = 1
                noTracksScrapedCount = 0
                trackRowsLen = 0
                while True:

                    # scrape track details for current page
                    print('page',pageNum,'-----------------------------------------------')                
                    for tag in page.findAll('a'):
                        #print(tag)
                        href = tag.get('href')
                        #print(href)
                        if href:
                            if '/albums/' in href:
                                if '?trackAsin=' in href:
                                    if trackUrl == '':
                                        trackUrl = href
                                        trackName = tag.contents[0]
                                    else:
                                        fatalError('new track row before getting previous')
                                else:
                                    if albumUrl == '' and trackLength == '':
                                        albumUrl = href
                                        albumName = tag.contents[0]
                                        trackLength = tag.parent.parent.next_sibling.text
                                    else:
                                        fatalError('new track row before getting previous')
                            elif '/artists/' in href:
                                if artistUrl == '':
                                    artistUrl = href
                                    artistName = tag.contents[0]
                                else:
                                    fatalError('new track row before getting previous')

                        if trackName and trackLength and albumName and artistName:
                            if addToURLList(playlistTrackIds, playlistTitle+'|'+trackName+'|'+trackLength+'|'+albumName+'|'+artistName):                               
                                trackRow = {'playlistUrl':playlistUrl,'playlistTitle':playlistTitle,\
                                            'trackUrl':trackUrl,'trackNum':str(trackNum).zfill(4),'trackName':trackName,'trackLength':trackLength,\
                                            'albumUrl':albumUrl,'albumName':albumName,\
                                            'artistUrl':artistUrl,'artistName':artistName}
                                trackRows.append(trackRow)
                                trackNum += 1
                            trackUrl = trackName = trackLength = albumUrl = albumName = artistUrl = artistName = ''

                    # give per page scraping status
                    tracksScraped = len(trackRows) - trackRowsLen
                    if tracksScraped:
                        trackRowsLen = len(trackRows)
                        noTracksScrapedCount = 0
                    else:
                        noTracksScrapedCount += 1
                    print('got %d tracks for page %d, %d total tracks'%(tracksScraped, pageNum, trackRowsLen))

                    # exit scraping on 3 page downs in a row with no new tracks
                    if noTracksScrapedCount > 3:
                        if len(trackRows) > 0:
                            with open('tracks.csv', 'a', newline='', encoding="utf-8") as tracksFile:
                                writer = csv.DictWriter(tracksFile, trackFields)
                                writer.writerows(trackRows)
                                trackRows = []                        
                        break

                    # page down and load new HTML
                    body = getWebPage.browser.find_element(By.CSS_SELECTOR,'body')
                    body.send_keys(Keys.PAGE_DOWN)
                    pageNum += 1
                    time.sleep(3.14)
                    html = getWebPage.browser.page_source
                    page = BeautifulSoup(html, features="html.parser")

            else:
                print('Could not get page:', url)

def loginToAmazon():
    page, success = getWebPage('https://music.amazon.com/my/playlists/all')
    input("Login to Amazon then press Enter here (in the terminal) to continue...")

########################################################################################################################
# main
#
if getPlaylists or getPlaylistTracks:
    browserStartup()
    loginToAmazon()

pushDir(accountName)
getAmazonPlaylists()
popDir()

if getPlaylists or getPlaylistTracks:
    browserShutdown()

vprint('\ndone!')