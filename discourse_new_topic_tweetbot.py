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

# Authenticate to Discourse & Create API object
discourse_api = discourse.Client(
    host=config('DISCOURSE_HOST'),
    api_username=config('DISCOURSE_API_USER'),
    api_key=config('DISCOURSE_API_KEY')
    )

# Authenticate to Twitter & Create API object
auth = tweepy.OAuthHandler(
    config('TWITTER_API_KEY'),
    config('TWITTER_API_SECRET_KEY')
    )
auth.set_access_token(
    config('TWITTER_ACCESS_TOKEN'),
    config('TWITTER_ACCESS_TOKEN_SECRET')
    )
twitter_api = tweepy.API(auth, wait_on_rate_limit=True,
            wait_on_rate_limit_notify=True)
try:
    twitter_api.verify_credentials()
except Exception as e:
    logger.error("Error creating API", exc_info=True)
    raise e
logger.debug("Tweepy Twitter API created")

# Get Bot Settings

DISCOURSE_HOST            = config('DISCOURSE_HOST')
DISCOURSE_SHARED_PATH     = config('DISCOURSE_SHARED_PATH', default='/var/discourse/shared/standalone')
DISCOURSE_NEWEST_TOPIC_ID = config('DISCOURSE_NEWEST_TOPIC_ID', default=1, cast=int)
POLLING_INTERVAL          = config('POLLING_INTERVAL', default=10, cast=int)
TWEET_USE_THUMBNAILS      = config('TWEET_USE_THUMBNAILS', default=1, cast=bool)
TWEET_STRING              = config('TWEET_STRING')
TWEET_MENTIONS            = config('TWEET_MENTIONS')
TWEET_HASHTAGS            = config('TWEET_HASHTAGS')

# Classes & Methods section
# note: bot handles only one Tweet at a time, so expect lots of ugly globals. 

class FindTwitterMentions(HTMLParser):
    """ Class inherits from HTMLParser to find Twitter mentions. """
    def handle_data(self, data):
        """ Search for specific strings for mentions & hashtags. Intended use: 
            mentions & hashtags within a Discourse post are hyperlinked causing
            BBCode to separate them with linebreaks in the cooked post."""
        global tweet_mentions
        global tweet_hashtags

        # customizations go here:
        if (    data.find('With ') > -1 or 
                data.find('By ')  > -1 or
                data.find('For ') > -1 ):
            tweet_mentions += data.lstrip()
        if data.find('@') > -1:
            tweet_mentions += data
        if data.find('#') > -1:
            tweet_hashtags += data
        # logging.debug ("«"+data+"»")

mentions_parser = FindTwitterMentions()

def build_tweet():
    global queued_topic
    global tweet_string 
    global tweet_mentions
    global tweet_hashtags
    global thumbnail_filename
    tweet_string = TWEET_STRING
    tweet_hashtags = TWEET_HASHTAGS
    tweet_mentions = TWEET_MENTIONS
    thumbnail_filename = None

    if hasattr(queued_topic, 'excerpt'):
        mentions_parser.feed(queued_topic.excerpt)

    # customizations go here:
    tweet_string += tweet_hashtags + "\n"
    tweet_string += queued_topic.title + "\n"
    tweet_string += tweet_mentions + "\n"
    tweet_string += DISCOURSE_HOST
    tweet_string += queued_topic.slug+"/"+str(queued_topic.id)

    if TWEET_USE_THUMBNAILS and queued_topic.image_url:
        thumbnail_filename=queued_topic.image_url.replace(DISCOURSE_HOST,DISCOURSE_SHARED_PATH)

def find_newest_topic():
    """ Find the newest Discourse topic *in the latest topics* from latest.json. """
    global queued_topic
    global newest_topic_id
    latest_topics           = discourse_api.get_latest_topics('default')
    newest_topic_index      = 0
    compar_topic_created_at = latest_topics[newest_topic_index].created_at
    try:
        queued_topic
    except NameError: #on bot startup, does not exist
        queued_topic = latest_topics[newest_topic_index]
        newest_topic_id = latest_topics[newest_topic_index].id

    for index, topic in enumerate(latest_topics):
        if topic.created_at > compar_topic_created_at:
            compar_topic_created_at = topic.created_at
            newest_topic_index = index
        if topic.id == queued_topic.id:
            queued_topic_index = index

    if latest_topics[newest_topic_index].id > newest_topic_id:
         newest_topic_id = latest_topics[newest_topic_index].id

    if newest_topic_id > queued_topic.id:
         queued_topic = latest_topics[newest_topic_index] 
    else:     
         queued_topic = latest_topics[queued_topic_index] # re-populate this object for thumbnails

# MAIN

def main():
    last_tweeted_topic_id = DISCOURSE_NEWEST_TOPIC_ID
    find_newest_topic()

    if stdin.isatty():
        build_tweet()
        logging.info ("\nINTERACTIVE TEST: next tweet from Discourse topic "+str(queued_topic.id)+":"
                +"\n"+tweet_string)
        if TWEET_USE_THUMBNAILS and thumbnail_filename:
            logging.debug (thumbnail_filename)

    else:
        while True:
            logging.debug ("sleeping for POLLING_INTERVAL...")
            sleep(POLLING_INTERVAL*60)
            find_newest_topic()
            if queued_topic.id > last_tweeted_topic_id: 
                logging.info (' '.join(['Tweet topic ',str(queued_topic.id),queued_topic.title]))
                build_tweet()
                if TWEET_USE_THUMBNAILS and thumbnail_filename:
                    logging.info (' '.join(['thumbnail:',thumbnail_filename]))
                    twitter_api.update_with_media(thumbnail_filename, tweet_string)
                else:
                    twitter_api.update_status(tweet_string)
                last_tweeted_topic_id = queued_topic.id 
            else:
                logging.debug ("nothing to tweet")

if __name__ == "__main__":
    main()
