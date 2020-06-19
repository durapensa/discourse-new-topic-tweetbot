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
from sys import stdin,argv,exit
from readchar import readkey

try:
    logger_hostname = {'hostname':config('DISCOURSE_HOST').partition("//")[2]}
except:
    exit(argv[0]+' exited. settings.ini configuration incorrect or incomplete for DISCOURSE_HOST.')

logger = logging.getLogger(__name__)
streamhandler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s %(hostname)s %(levelname)s: %(message)s', "%Y-%m-%d %H:%M:%S")
streamhandler.setFormatter(formatter)
logger.setLevel(logging.INFO)
logger.addHandler(streamhandler)
logger = logging.LoggerAdapter(logger, logger_hostname)

def authenticate():
    """ Authenticate to Discourse & Twitter and create API object. """
    global discourse_api
    global twitter_api

    try:
        discourse_api = discourse.Client(
            host=config('DISCOURSE_HOST'),
            api_username=config('DISCOURSE_API_USER'),
            api_key=config('DISCOURSE_API_KEY')
            )
    except Exception as e:
        logger.error("ERROR creating Discourse API for "
                +config('DISCOURSE_API_USER'), exc_info=True)
        raise e
    else:
        logger.info("Discourse API created for @"
                +config('DISCOURSE_API_USER'))

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
        logger.error("ERROR creating Twitter API for @"
                +config('TWITTER_API_USER') , exc_info=True)
        raise e
    else:
        logger.info("Twitter API created for @"
            +config('TWITTER_API_USER'))

def get_settings():
    """ Get Bot settings. """
    global DISCOURSE_HOST
    global DISCOURSE_SHARED_PATH
    global DISCOURSE_NEWEST_TOPIC_ID
    global POLLING_INTERVAL
    global TOPIC_REFRESH_INTERVAL
    global TWEET_USE_THUMBNAILS
    global TWEET_PREPEND
    global TWEET_MENTIONS
    global TWEET_HASHTAGS

    DISCOURSE_HOST            = config('DISCOURSE_HOST')
    DISCOURSE_SHARED_PATH     = config('DISCOURSE_SHARED_PATH', default='/var/discourse/shared/standalone')
    DISCOURSE_NEWEST_TOPIC_ID = config('DISCOURSE_NEWEST_TOPIC_ID', default=1, cast=int)
    POLLING_INTERVAL          = config('POLLING_INTERVAL', default=10, cast=int)
    TOPIC_REFRESH_INTERVAL    = config('TOPIC_REFRESH_INTERVAL', default=8, cast=int)
    TWEET_USE_THUMBNAILS      = config('TWEET_USE_THUMBNAILS', default=1, cast=bool)
    TWEET_PREPEND             = config('TWEET_STRING')
    TWEET_MENTIONS            = config('TWEET_MENTIONS')
    TWEET_HASHTAGS            = config('TWEET_HASHTAGS')

class HTMLMentionsParser(HTMLParser):
    """ Class inherits from HTMLParser to find Twitter mentions. """
    def handle_data(self, data):
        """ Search for specific strings for mentions & hashtags. Intended use: 
            mentions & hashtags within a Discourse post are hyperlinked causing
            BBCode to separate them with linebreaks in the cooked post. Globals
            are hacky until this class & its methods are better understood."""
        global tweet_mentions
        global tweet_hashtags

        # customizations go here:
        if (    data.find('With ') > -1 or 
                data.find('By ')  > -1 or
                data.find('Created by ')  > -1 or
                data.find('For ') > -1 ):
            tweet_mentions += data
        if data.find('@') > -1:
            tweet_mentions += data
        if data.find('#') > -1:
            tweet_hashtags += data
        #logger.info ("«"+data+"»")

parse_twitter_mentions = HTMLMentionsParser()

def build_tweet_string(topic):
    """ Builds a tweet. """
    global tweet_hashtags
    global tweet_mentions
    tweet_prepend  = TWEET_PREPEND
    tweet_hashtags = TWEET_HASHTAGS
    tweet_mentions = TWEET_MENTIONS

    parse_twitter_mentions.feed(topic.post_stream['posts'][0]['cooked'])
    parse_twitter_mentions.close

    # customizations go here:
    tweet_string  = tweet_prepend
    tweet_string += tweet_hashtags + "\n"
    tweet_string += topic.title + "\n"
    tweet_string += tweet_mentions + "\n"
    tweet_string += DISCOURSE_HOST+"/t/"
    tweet_string += topic.slug+"/"+str(topic.id)

    return tweet_string

def enque_newest_topics(queued_topics_len, newest_topic_id):
    """ Find the newest Discourse topics *among the latest topics* from
        latest.json and appends them to queued_topics for tweeting. 
        Note: keeping queued_topics global so it's not copied around every
        N minutes."""
    global queued_topics
    try:
        latest_topics       = discourse_api.get_latest_topics('default')
    except:
        logger.info("Failed to retrieve latest topics from Discourse server")
        return

    for topic in latest_topics:
        if topic.id > newest_topic_id:
            queued_topics.append(topic)

    if len(queued_topics) > queued_topics_len:
        logger.info ("Added "+str(len(queued_topics)-queued_topics_len)+' item(s) to queue')
        queued_topics.sort(queued_topics.id, reverse=True)
        newest_topic_id = queued_topics[0].id
        queued_topics_len = len(queued_topics)

    return queued_topics_len, newest_topic_id

def review_topic(topic_id):
    try:
        # Get the full topic, not the truncated one from latest_topics
        topic = discourse_api.get_topic(topic_id)
    except:
        logger.info("Failed to get topic "+str(topic_id)+" from Discourse server.")
        return
 
    media_string = ""
    tweet_string = build_tweet_string(topic)
    if TWEET_USE_THUMBNAILS and topic.image_url:
        media_string = "WITH MEDIA inclusion:\n"
        media_string += topic.image_url+"\n"
        media_string += topic.image_url.replace(DISCOURSE_HOST,DISCOURSE_SHARED_PATH)+"\n"
    logger.info ("\n\n"+tweet_string+"\n\n"+media_string)
    logger.info ("Tweet topic "+str(topic.id)+"? (y/n/q)?")
    user_answer = readkey()
    if user_answer.lower() == 'y':
        tweet(topic)
    elif user_answer.lower() == 'q':
        exit()

def review_latest_topics():
    logger.info("======= ⟫⟫⟫ Interactive testing mode ⟪⟪⟪ =======")
    logger.info("Latest Discourse topics, sorted newest to oldest by creation date:")
    try:
        latest_topics       = discourse_api.get_latest_topics('default')
        latest_topics.sort(key=lambda topic: topic.created_at, reverse=True)
    except:
        logger.info("Failed to retrieve latest topics from Discourse server")
        return

    for index, topic in enumerate(latest_topics):
        review_topic(topic.id)

def tweet(topic):
    tweet_string = build_tweet_string(topic)

    if TWEET_USE_THUMBNAILS and topic.image_url:
        thumbnail_path=topic.image_url.replace(DISCOURSE_HOST,DISCOURSE_SHARED_PATH)

        try:
            twitter_api.update_with_media(thumbnail_path, tweet_string)
        except:
            logger.info ("TWEET FAILED topic "+str(topic.id)+" "+topic.title)
            return False
        else: 
            logger.info ("TWEETED topic "+str(topic.id)+" "+topic.title)
            return True

    else:
        try:
            twitter_api.update_status(tweet_string)
        except:
            logger.info ("TWEET FAILED topic "+str(topic.id)+" "+topic.title)
            return False
        else: 
            logger.info ("TWEETED topic "+str(topic.id)+" "+topic.title)
            return True

def main():
    global queued_topics
    global logger
    authenticate()
    get_settings()
    queued_topics = []
    queued_topics_len = -1

    if stdin.isatty():
        review_latest_topics()

    else:
        while True:
            if queued_topics_len == -1:
                try:
                    latest_topics       = discourse_api.get_latest_topics('default')
                except:
                    logger.info("Failed to retrieve latest topics from Discourse server.")
                    logger.info("Sleeping for latest topics polling interval of "+POLLING_INTERVAL+" mins.")
                    sleep(POLLING_INTERVAL*60)
                    continue

                latest_topics.sort(key=lambda topic: topic.created_at, reverse=True)
                newest_topic_id = latest_topics[0].id
                queued_topics_len = 0

            if queued_topics_len > 0:
                logger.info (str(queued_topics_len)+" topic(s) to tweet.")
                logger.info ("Sleeping for topic refresh interval of "+str(TOPIC_REFRESH_INTERVAL)+" min...")
                queued_topic = queued_topics[len(queued_topics)-1]
                sleep(TOPIC_REFRESH_INTERVAL*60)
                topic_refresh_interval = 0
                try:
                    queued_topic = discourse_api.get_topic(queued_topic.id)
                except:
                    logger.info ("Failed to refresh latest topic from Discourse server")
                    continue
                else:
                    if tweet(queued_topic):
                        queued_topics.remove[len(queued_topics)-1]
                        queued_topics_len -= 1
            else:
                logger.info ("0 new topic(s) to tweet.")
                topic_refresh_interval = TOPIC_REFRESH_INTERVAL

            logger.info ("Sleeping for latest topics polling interval of "
                    +str(max(min(POLLING_INTERVAL,TOPIC_REFRESH_INTERVAL),POLLING_INTERVAL-topic_refresh_interval))
                    +" min...")
            sleep (max(min(POLLING_INTERVAL*60,TOPIC_REFRESH_INTERVAL*60),POLLING_INTERVAL*60-topic_refresh_interval*60))
            queued_topics_len, newest_topic_id = enque_newest_topics(queued_topics_len, newest_topic_id)

if __name__ == "__main__":
    main()
