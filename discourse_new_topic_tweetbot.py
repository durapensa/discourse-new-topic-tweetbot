#!/usr/bin/env python3
"""
discourse_new_topic_tweetbot.py
===============================
"""
import discourse
import tweepy
import requests
import logging
from decouple import config
from html.parser import HTMLParser
from time import sleep
from sys import stdin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

def authenticate():
    """ Authenticate to Discourse & Twitter and create API object. """
    global discourse_api
    global twitter_api

    discourse_api = discourse.Client(
        host=config('DISCOURSE_HOST'),
        api_username=config('DISCOURSE_API_USER'),
        api_key=config('DISCOURSE_API_KEY')
        )

    twitter_auth = tweepy.OAuthHandler(
        config('TWITTER_API_KEY'),
        config('TWITTER_API_SECRET_KEY')
        )
    twitter_auth.set_access_token(
        config('TWITTER_ACCESS_TOKEN'),
        config('TWITTER_ACCESS_TOKEN_SECRET')
        )
    twitter_api = tweepy.API(twitter_auth, wait_on_rate_limit=True,
            wait_on_rate_limit_notify=True)
    try:
        twitter_api.verify_credentials()
    except Exception as e:
        logger.error("Error creating API", exc_info=True)
        raise e
    else:
        logger.debug("Tweepy Twitter API created")

def get_settings():
    """ Get Bot settings. """
    global DISCOURSE_HOST
    global DISCOURSE_SHARED_PATH
    global DISCOURSE_NEWEST_TOPIC_ID
    global POLLING_INTERVAL
    global TWEET_REFRESH_INTERVAL
    global TWEET_USE_THUMBNAILS
    global TWEET_STRING
    global TWEET_MENTIONS
    global TWEET_HASHTAGS

    DISCOURSE_HOST            = config('DISCOURSE_HOST')
    DISCOURSE_SHARED_PATH     = config('DISCOURSE_SHARED_PATH', default='/var/discourse/shared/standalone')
    DISCOURSE_NEWEST_TOPIC_ID = config('DISCOURSE_NEWEST_TOPIC_ID', default=1, cast=int)
    POLLING_INTERVAL          = config('POLLING_INTERVAL', default=10, cast=int)
    TWEET_REFRESH_INTERVAL      = config('TWEET_REFRESH_INTERVAL', default=8, cast=int)
    TWEET_USE_THUMBNAILS      = config('TWEET_USE_THUMBNAILS', default=1, cast=bool)
    TWEET_STRING              = config('TWEET_STRING')
    TWEET_MENTIONS            = config('TWEET_MENTIONS')
    TWEET_HASHTAGS            = config('TWEET_HASHTAGS')

class HTMLMentionsParser(HTMLParser):
    """ Class inherits from HTMLParser to find Twitter mentions. """
    def handle_data(self, data):
        """ Search for specific strings for mentions & hashtags. Intended use: 
            mentions & hashtags within a Discourse post are hyperlinked causing
            BBCode to separate them with linebreaks in the cooked post."""
        global tweet_mentions
        global tweet_hashtags
        tweet_hashtags = TWEET_HASHTAGS
        tweet_mentions = TWEET_MENTIONS

        # customizations go here:
        if (    data.find('With ') > -1 or 
                data.find('By ')  > -1 or
                data.find('For ') > -1 ):
            tweet_mentions += data.lstrip()
        if data.find('@') > -1:
            tweet_mentions += data
        if data.find('#') > -1:
            tweet_hashtags += data
        # logger.debug ("«"+data+"»")

parse_twitter_mentions = HTMLMentionsParser()

def build_tweet_string():
    """ Builds a tweet from queued_topic. """
    tweet_string = TWEET_STRING

    try:
        queued_topic
    except NameError:
        logger.info('no queued topic')
        #pass
    else:
        if hasattr(queued_topic, 'excerpt'):
            parse_twitter_mentions.feed(queued_topic.excerpt)

        # customizations go here:
        tweet_string += tweet_hashtags + "\n"
        tweet_string += queued_topic.title + "\n"
        tweet_string += tweet_mentions + "\n"
        tweet_string += DISCOURSE_HOST+"/t/"
        tweet_string += queued_topic.slug+"/"+str(queued_topic.id)

    return tweet_string

def enque_newest_topics():
    """ Find the newest Discourse topics *among the latest topics* from
        latest.json and appends them to queued_topics for tweeting. """
    global queued_topics
    global queued_topics_len
    latest_topics           = discourse_api.get_latest_topics('default')
    newest_topic_index      = 0
    compar_topic_created_at = latest_topics[newest_topic_index].created_at
    
    if queued_topics_len == -1:
        for index, topic in enumerate(latest_topics):
            if topic.created_at > compar_topic_created_at:
                compar_topic_created_at = topic.created_at
                newest_topic_index = index

        if latest_topics[newest_topic_index].id > DISCOURSE_NEWEST_TOPIC_ID:
           queued_topics = [latest_topics[newest_topic_index]]
           queued_topics_len = 1

    # look for topics newer than those in queued_topic, add then then sort
    # there's probably a more pythonic way to do this!
    if queued_topics_len > -1:
        for topic in latest_topics:
            for qtopic in queued_topics:
                if topic.id > qtopic.id:
                    queued_topics.append(topic)
                    queued_topics_len += 1
     
        if len(queued_topics) > queued_topics_len:
            logger.info ('Added '+str(queued_topics_len)+' item(s) to queue')
            queued_topic.sort(queued_topics.id)

def go_interactive():
    try:
        queued_topic = queued_topics.pop()
    except NameError:
        logger.info ("\nINTERACTIVE TEST: No new Discourse topic to Tweet. ")
    else:
        tweet_string = build_tweet_string()
        logger.info ("\nINTERACTIVE TEST: next tweet from Discourse topic "+str(queued_topic.id)+":\n"+tweet_string)
        if TWEET_USE_THUMBNAILS and queued_topic.image_url:
            logger.debug ("MEDIA INCLUSION from: ",queued_topic.image_url)

def refresh_queued_topic():
    global queued_topic
    queued_topic = discourse_api.get_topic(queued_topic[0].id)

def tweet_queued_topic():
    tweet_string = build_tweet_string()

    if TWEET_USE_THUMBNAILS and queued_topic.image_url:
        thumbnail_path=queued_topic.image_url.replace(DISCOURSE_HOST,DISCOURSE_SHARED_PATH)

        try:
            twitter_api.update_with_media(thumbnail_path, tweet_string)
        except:
            logger.info (' TWEET FAILED'.join([' topic ',str(queued_topic.id),queued_topic.title]))
        else: 
            logger.info (' TWEETED'.join([' topic ',str(queued_topic.id),queued_topic.title]))

    else:
        try:
            twitter_api.update_status(tweet_string)
        except:
            logger.info (' TWEET FAILED'.join([' topic ',str(queued_topic.id),queued_topic.title]))
        else: 
            logger.info (' TWEETED'.join([' topic ',str(queued_topic.id),queued_topic.title]))

def main():
    global queued_topic
    global queued_topics_len
    authenticate()
    get_settings()
    queued_topics_len = -1
    enque_newest_topics()

    if stdin.isatty():
        go_interactive()
    else:
        while True:
            if queued_topics_len > 0:
                queued_topic = queued_topics.pop()
                queued_topics_len -= 1
                logger.info (queued_topics_len+" new topic(s) to tweet!\nSleeping for TWEET_REFRESH_INTERVAL...")
                sleep(TWEET_REFRESH_INTERVAL*60)
                tweet_refresh_interval = 0
                refresh_queued_topic()
                tweet_queued_topic()
            else:
                logger.info ("No new topics to tweet..")
                tweet_refresh_interval = TWEET_REFRESH_INTERVAL
            logger.info ("Sleeping for POLLING_INTERVAL...")
            sleep(max(0,POLLING_INTERVAL*60-tweet_refresh_interval*60))
            enque_newest_topics()

if __name__ == "__main__":
    main()
