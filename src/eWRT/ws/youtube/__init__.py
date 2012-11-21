#!/usr/bin/env python
# coding: UTF-8
'''
Created on 25.09.2012

@author: Norman Süsstrunk, Heinz-Peter Lang, Albert Weichselbraun
'''
import unittest
import logging
from operator import attrgetter
from datetime import datetime, timedelta

from gdata.youtube.service import YouTubeService, YouTubeVideoQuery
from eWRT.ws.WebDataSource import WebDataSource

MAX_RESULTS_PER_QUERY = 50 
logger = logging.getLogger('eWRT.ws.youtube')

# ToDO: comment rating, once it get's supported by the gdata API.
# TODO: query.location --> radius available?


class YouTube(WebDataSource):
    '''
    searches youtube video library
    '''
    
    YT_ATOM_RESULT_TO_DICT_MAPPING = {
        'media.title.text': 'title',
        'published.text':'published',
        'media.description.text': 'content',
        'media.keywords.text':'keywords',
        'media.duration.seconds':'duration', 
        'rating.average': 'average rating', 
        'statistics.view_count': 'statistics_viewcount', 
        'statistics.favorite_count': 'statistics_favoritecount', 
        'rating.average': 'rating_average',
        'rating.max': 'rating_max',
        'rating.min': 'rating_min',
        'rating.num_raters': 'rating_numraters', 
        'summary': 'summary', 
        'rights': 'rights', 
        'updated.text': 'last_modified', 
        'source': 'yt_source'
    }
    
    def __init__(self):
        self.youtube_service = YouTubeService()

        
    def search(self, search_terms, location=None, 
               max_results=MAX_RESULTS_PER_QUERY, max_age=None,
               orderby= 'published',
               max_comment_count=0):
        """ 
        Searches for youtube videos.
        
        @param search_terms: list of search terms
        @param location: tuple latitude, longitue, e.g. 37.42307,-122.08427
        @param max_results:
        @param max_age: datetime of the oldest entry  
        @param orderby: order search results by (relevance, published, viewCount, rating)
        @param max_comment_count: maximum number of comments to fetch (default: 0)
        """
        
        # all youtube search parameter are here: 
        # https://developers.google.com/youtube/2.0/reference?hl=de#Custom_parameters
        query = YouTubeVideoQuery()
        query.vq = ', '.join(search_terms)
        query.orderby = orderby
        query.racy = 'include'
        query.time = self.get_query_time(max_age)
        query.max_results = MAX_RESULTS_PER_QUERY

        if location:
            query.location = location
                        
        return self.search_youtube(query, max_results, max_comment_count)
    

    @classmethod
    def get_query_time(cls, max_age):
        ''' converts a datetime or int (age in minutes) to the youtube specific
        query parameter (e.g. this_month, today ...)
        @param max_age: int or datetime object
        @return: youtube specific query_time 
        '''
        if not max_age:
            return 'all_time'
        
        if isinstance(max_age, datetime):
            # convert datetime to minutes
            max_age = (datetime.now() - max_age).total_seconds() / 60  

        if max_age <= 1440:
            query_time = 'today'
        elif max_age > 1440 and max_age <= 10080:
            query_time = 'this_week'
        else: 
            query_time = 'this_month'
            
        return query_time
    
    
    def search_youtube(self, query, max_results=MAX_RESULTS_PER_QUERY, 
                       max_comment_count=0):
        ''' executes the youtube query and facilitates paging of the resultset
        @param query: YouTubeVideoQuery
        @param max_results: 
        @param max_comment_count: maximum number of comments to fetch
        @return: list of dictionaries 
        '''
        result = []
        feed = self.youtube_service.YouTubeQuery(query)
        
        while feed:
                        
            for entry in feed.entry: 
                try: 
                    yt_dict = self.convert_feed_entry(entry, max_comment_count)
                    result.append(yt_dict)
                except Exception, e: 
                    logger.exception('Exception converting entry: %s' % e)
                    
                if len(result) == max_results:
                    return result
                
            if not feed.GetNextLink():
                break
            
            feed = self.youtube_service.Query(feed.GetNextLink().href)
            
        return result


    def convert_feed_entry(self, entry, max_comment_count):
        ''' 1. converts the feed entry to a dictionary (never change the mapping
               names, as later analyzer steps requires consistent keys)
            2. fetches comments and integrate them in the dictionary, if necessary
            
            @param entry: Youtube feed entry
            @param max_comment_count: maximum number of comments to fetch
            @return: dictionary   
        '''
        yt_dict = {'user_name': entry.author[0].name.text, 
                   'user_url': entry.author[0].uri.text}
        
        for attr, key in self.YT_ATOM_RESULT_TO_DICT_MAPPING.items(): 
            try: 
                yt_dict[key] = attrgetter(attr)(entry)
            except AttributeError, e:
                logger.warn('AttributeError: %s' % e)
                yt_dict[key] = None
                
        yt_dict['id'] = entry.id.text.split('/')[-1]
        yt_dict['url'] = "http://www.youtube.com/watch?v=%s" % yt_dict['id']         
        
        # the hasattr is required for compatibility with older videos
        yt_dict['location'] = entry.geo.location() \
            if hasattr(entry, 'geo') and entry.geo else None
        
        yt_dict['related_url'] = None
        for link in entry.link:
            if link.href.endswith('related'):
                yt_dict['related_url'] = link.href
        
        if yt_dict['duration']: 
            duration = int(yt_dict['duration'])
            yt_dict['duration'] = '%d:%02d' % (duration / 60, duration % 60)
        
        yt_dict['picture'] = None
        if hasattr(entry, 'media'):
            for thumbnail in entry.media.thumbnail:
                yt_dict['picture'] = thumbnail.url
                break

        if not yt_dict['keywords']: 
            yt_dict['keywords'] = []

        for category in entry.category:
            if 'http://gdata.youtube.com/schemas' not in category.term:
                yt_dict['keywords'].append(category.term)

        # retrieve comments, if required
        if max_comment_count > 0:
            yt_dict['comments'] = self.get_video_comments( yt_dict['id'],
                                                            max_comment_count )

        return yt_dict


    def get_video_comments(self, video_id, max_comments=25):
        """ @param video_id: the video_id of the video for which we want to retrieve
                        the comments.
            @param max_comments: maximum number of comments to retrieve
            @return: a list of comments 
        """
        comments = []
        comment_feed = self.youtube_service.GetYouTubeVideoCommentFeed(
                            video_id=video_id)
        
        while comment_feed:
            
            for comment in comment_feed.entry:
                url, in_reply_to = self.get_relevant_links( comment )
                comments.append( {'id' : comment.id.text,
                                  'url': url,
                                  'in-reply-to' : in_reply_to,
                                  'author': comment.author[0].name.text,
                                  'title' : comment.title.text,
                                  'published': comment.published.text,
                                  'updated'  : comment.updated.text,
                                  'content'  : comment.content.text}
                                )
                if len(comments) == max_comments:
                    return comments
                
            # retrieve the next comment page, if available
            if not comment_feed.GetNextLink():
                break
           
            comment_feed = self.youtube_service.Query(
                                    comment_feed.GetNextLink().href)
        
        return comments


    @staticmethod
    def get_relevant_links( comment ):
        """ @param comment: a single YouTube comment.
            @return: a tuple indicating:
                       a) the comment's url, and 
                       b) the url of the comment to which this comment refers (in case
                          it is a reply)
        """
        comment_url, in_reply_to = None, None
        for link in comment.link:
            if link.rel == 'self':
                comment_url = link.href
            elif link.rel.endswith("#in-reply-to"):
                in_reply_to = link.href

        return comment_url, in_reply_to        

                                     

class YouTubeTest(unittest.TestCase):
        
    def setUp(self):
        self.search_terms = ["Linus Torvalds","Ubuntu"]
        self.youtube = YouTube()
    
    def test_query_time(self):
        test_cases = ((1000, 'today'), 
                      (5000, 'this_week'), 
                      (12000, 'this_month'), 
                      (datetime.now() - timedelta(hours=12), 'today'),
                      (datetime.now() - timedelta(days=4), 'this_week'),
                      (datetime.now() - timedelta(days=15), 'this_month'),)
        
        for max_age, exp_result in test_cases: 
            result = YouTube.get_query_time(max_age)
            assert exp_result == result, 'max_age %s, result %s, exp %s' % (max_age, 
                                                                            result, 
                                                                            exp_result)
        
    
    def test_search(self):   
        required_keys = ('location', 'content', 'id', 'url', 'title',
                         'last_modified', 'published', 'user_name', 
                         'yt_source', 'rights', 'summary', 'keywords', 
                         'related_url', 'statistics_viewcount', 
                         'statistics_favoritecount', 'rating_average', 
                         'rating_max', 'rating_min', 'rating_numraters', 
                         'picture', 'duration', 'user_url'
                        )
             
        for r in self.youtube.search(self.search_terms, None):

            assert len(required_keys) == len(r.keys())
            
            for rk in required_keys: 
                if not rk in r.keys():
                    print 'k ', sorted(r.keys())
                    print 'rk', sorted(required_keys)
                    assert False, 'key %s missing' % rk

    def test_comments_result(self):
        search_terms = ((('Linux',), 5), (('Apple',), 3), (('Microsoft',), 2))
        
        for search_term, max_results in search_terms:
            print 'querying youtube for %s' % search_term
            result = self.youtube.search(search_term, None, max_results, orderby='relevance', max_comment_count=5)
            print '\t got %s documents, max_results was %s' % (len(result),
                                                               max_results) 
            assert len(result) == max_results
            assert max( [ len(r['comments']) for r in result ] ) == 5
            print '-------------------------'
            
    def test_paging(self):
        result = self.youtube.search( ("Linux"), None, max_results=200)
        assert len(result) == 200
        
    def test_comments(self):
        comments = self.youtube.get_video_comments(video_id="yI4g8Ti6eTM", 
                                             max_comments = 27)
        assert len(comments) == 27
        
        
if __name__ == "__main__":
    unittest.main()
        