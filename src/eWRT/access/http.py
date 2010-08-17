#!/usr/bin/env python

""" @package eWRT.access.http
    provides access to resources using http """

# (C)opyrights 2008-2010 by Albert Weichselbraun <albert@weichselbraun.net>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import urllib2
from eWRT.config import USER_AGENT, DEFAULT_WEB_REQUEST_SLEEP_TIME, PROXY_SERVER
from urlparse import urlsplit
import time
from StringIO import StringIO
from gzip import GzipFile

from nose.tools import raises
from nose.plugins.attrib import attr

getHostName = lambda x: "://".join( urlsplit(x)[:2] )

# set default socket timeout (otherwise urllib might hang!)
from socket import setdefaulttimeout
setdefaulttimeout(60)

class Retrieve(object):
    """ @class Retrieve
        retrieves URLs using HTTP 

        @remarks: 
        this class supports transparent
        * authentication and
        * compression 
    """

    __slots__ = ('module', 'sleep_time', 'last_access_time', 'user_agent')

    def __init__(self, module, sleep_time=DEFAULT_WEB_REQUEST_SLEEP_TIME):
        self.module           = module
        self.sleep_time       = sleep_time
        self.last_access_time = 0
        
        self.user_agent = USER_AGENT % self.module \
                            if "%s" in USER_AGENT else USER_AGENT


    def open(self, url, data=None, user=None, pwd=None ):
        """ Opens an URL and returns the matching file object 
            @param[in] url 
            @param[in] data  optional data to submit
            @param[in] user  optional user name
            @param[in] pwd   optional password
            @returns a file object for reading the url
        """
        request = urllib2.Request( url, data )
        request.add_header( 'User-Agent', self.user_agent )
        request.add_header('Accept-encoding', 'gzip')
        self._throttle()

        opener = []
        if PROXY_SERVER:
            opener.append( urllib2.ProxyHandler({"http" :PROXY_SERVER} ) )
        if user and pwd:
            opener.append( self._getHTTPBasicAuthOpener(url, user, pwd) )

        urllib2.install_opener( urllib2.build_opener( *opener ) )
        urlObj = urllib2.urlopen( request )

        # check whether the data stream is compressed
        if urlObj.headers.get('Content-Encoding') == 'gzip':
            return self._getUncompressedStream( urlObj )

        return urlObj

    @staticmethod
    def _getHTTPBasicAuthOpener(url, user, pwd):
        """ returns an opener, capable of handling http-auth """
        auth_handler = urllib2.HTTPBasicAuthHandler()
        auth_handler.add_password('realm', getHostName(url), user, pwd)
        return auth_handler

    @staticmethod
    def _getUncompressedStream(urlObj):
        """ transparently uncompressed the given data stream
            @param[in] urlObj 
            @returns an urlObj containing the uncompressed data
        """
        compressedStream = StringIO( urlObj.read() )
        return GzipFile(fileobj=compressedStream) 

    def _throttle( self ):
        """ delays web access according to the content provider's policy """
        if (time.time() - self.last_access_time) < DEFAULT_WEB_REQUEST_SLEEP_TIME:
            time.sleep( self.sleep_time )
        self.last_access_time= time.time()


class TestRetrieve(object):
    """ tests the http class """
    TEST_URLS = ('http://www.google.at/search?hl=de&q=andreas&btnG=Google-Suche&meta=', 
                 'http://www.heise.de' )

    def __init__(self):
        from socket import getdefaulttimeout
        self.default_timeout = getdefaulttimeout()

    def tearDown(self):
        setdefaulttimeout( self.default_timeout )

    @attr("remote")
    def testRetrieval(self):
        """ tries to retrieve the following url's from the list """

        r_handler = Retrieve( self.__class__.__name__ )
        for url in self.TEST_URLS:
            print url
            r=r_handler.open( url )
            r.read()
            r.close()

    @attr("remote")
    @raises(urllib2.URLError)
    def testRetrievalTimeout(self):
        """ tests whether the socket timeout is honored by our class """
        SLOW_URL = "http://www.iub.edu.bd/"
        setdefaulttimeout( 1 )

        r = Retrieve( self.__class__.__name__).open( SLOW_URL )
        content = r.read()
        r.close()

    @attr("remote")
    def testMultiProcessing(self):
        """ verifies that retrieves works with multi-processing """
        from multiprocessing import Pool
        p = Pool(4)

        TEST_URLS = ['http://www.heise.de', 
                     'http://linuxtoday.com',
                     'http://www.kurier.at',
                     'http://www.diepresse.com',
                     'http://www.spiegel.de',
                     'http://www.sueddeutsche.de',
                    ]

        for res in  p.map(t_retrieve, TEST_URLS):
            assert len(res) > 20


def t_retrieve(url):
    """ retrieves the given url from the web
        
        @remarks
        helper module for the testMultiProcessing unit test.
    """
    r = Retrieve( __name__ ).open( url )
    content = r.read()
    r.close()

    return content

