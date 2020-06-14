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
from readchar import readkey
from pprint import pprint

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

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
        logger.error(config('DISCOURSE_HOST').partition("//")[2]
                +": ERROR creating Discourse API for "
                +config('DISCOURSE_API_USER'), exc_info=True)
        raise e
    else:
        logger.info(config('DISCOURSE_HOST').partition("//")[2]
                +": Discourse API created for user "
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
        logger.error(config('DISCOURSE_HOST').partition("//")[2]
                +": ERROR creating Twitter API for @"
                +config('TWITTER_API_USER') , exc_info=True)
        raise e
    else:
        logger.info(config('DISCOURSE_HOST').partition("//")[2]
            +": Twitter API created for @"
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
        #logger.info ("«"+data+"»")

parse_twitter_mentions = HTMLMentionsParser()

def build_tweet_string(topic):
    """ Builds a tweet. """
    global tweet_hashtags
    global tweet_mentions
    tweet_prepend = TWEET_PREPEND

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

def enque_newest_topics(queued_topics_len):
    """ Find the newest Discourse topics *among the latest topics* from
        latest.json and appends them to queued_topics for tweeting. 
        Note: keeping queued_topics global so it's not copied around every
        N minutes."""
    global queued_topics
    try:
        latest_topics       = discourse_api.get_latest_topics('default')
    except:
        logger.info(logger_prepend
                +"Failed to retrieve latest topics from Discourse server")

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
            logger.info (logger_prepend
                    +" Added "+str(len(queued_topics)-queued_topics_len)+' item(s) to queue')
            queued_topic.sort(queued_topics.id)

    return queued_topics_len

def review_latest_topics():
    logger.info(logger_prepend
            +"Fetching latest topics from Discourse server...")
    try:
        latest_topics       = discourse_api.get_latest_topics('default')
    except:
        logger.info(logger_prepend
                +"Failed to retrieve latest topics from Discourse server")

    for index, topic in enumerate(latest_topics):
        try:
            topic = discourse_api.get_topic(latest_topics[index].id)
        except:
            logger.info(logger_prepend
                    +"Failed to get topic from Discourse server")
        else:
            tweet_string = build_tweet_string(topic)
            logger.info (logger_prepend
                    +"Topic "+str(topic.id)+":\n"+tweet_string)
            if TWEET_USE_THUMBNAILS and topic.image_url:
                logger.info (topic.image_url.replace(DISCOURSE_HOST,DISCOURSE_SHARED_PATH))
            logger.info (logger_prepend
                    +"Show next topic (y/n/q)?")
            user_answer = readkey()
            if user_answer.lower() == 'y':
                pass
            else:
                break

def tweet(topic):
    tweet_string = build_tweet_string(topic)

    if TWEET_USE_THUMBNAILS and topic.image_url:
        thumbnail_path=topic.image_url.replace(DISCOURSE_HOST,DISCOURSE_SHARED_PATH)

        try:
            twitter_api.update_with_media(thumbnail_path, tweet_string)
        except:
            logger.info (logger_prepend
                    +"TWEET FAILED topic "+str(topic.id)+" "+topic.title)
        else: 
            logger.info (logger_prepend
                    +"TWEETED topic "+str(topic.id)+" "+topic.title)

    else:
        try:
            twitter_api.update_status(tweet_string)
        except:
            logger.info (logger_prepend
                    +"TWEET FAILED topic "+str(topic.id)+" "+topic.title)
        else: 
            logger.info (logger_prepend
                    +"TWEETED topic "+str(topic.id)+" "+topic.title)

def main():
    authenticate()
    get_settings()
    global logger_prepend
    logger_prepend    = DISCOURSE_HOST.partition("//")[2]+": "
    queued_topics_len = -1
    queued_topics_len = enque_newest_topics(queued_topics_len)

    if stdin.isatty():
        logger.info(logger_prepend
                +"⟫⟫⟫ Interactive testing mode ⟪⟪⟪  No tweets will be posted.")
        if queued_topics_len > 0:
            try:
                #get the full topic, not the truncated one from latest_topics
                topic = discourse_api.get_topic(queued_topics[0].id)
            except:
                logger.info(logger_prepend
                        +"Failed to get newest topic from Discourse server.")
            else:
                tweet_string = build_tweet_string(topic)
                logger.info (logger_prepend
                        +"Next tweet from Discourse topic "+str(topic.id)+":\n"+tweet_string)
                if TWEET_USE_THUMBNAILS and topic.image_url:
                    logger.info (topic.image_url.replace(DISCOURSE_HOST,DISCOURSE_SHARED_PATH))
        else:
            logger.info (logger_prepend
                    +"No new Discourse topic to Tweet.")

        logger.info (logger_prepend
                +"Iterate through all topics in latest topics (y/n/q)?")
        user_answer = readkey()
        if user_answer.lower() == 'y':
            review_latest_topics()

    else:
        while True:
            if queued_topics_len > 0:
                logger.info (logger_prepend
                        ++str(queued_topics_len)
                        +" new topic(s) to tweet. Refresh interval, sleeping for "
                        +str(TOPIC_REFRESH_INTERVAL)+" min...")
                queued_topic = queued_topics.pop()
                queued_topics_len -= 1
                sleep(TOPIC_REFRESH_INTERVAL*60)
                topic_refresh_interval = 0
                try:
                    queued_topic = discourse_api.get_topic(queued_topic.id)
                except:
                    logger.info (logger_prepend
                            +"Failed to refresh latest topic from Discourse server")
                else:
                    tweet(queued_topic)
            else:
                logger.info (logger_prepend
                        +"No new topics to tweet..")
                topic_refresh_interval = TOPIC_REFRESH_INTERVAL

            logger.info (logger_prepend
                    +"Polling interval, sleeping for "
                    +str(max(min(POLLING_INTERVAL,TOPIC_REFRESH_INTERVAL),POLLING_INTERVAL-topic_refresh_interval))
                    +" min...")
            sleep (max(min(POLLING_INTERVAL*60,TOPIC_REFRESH_INTERVAL*60),POLLING_INTERVAL*60-topic_refresh_interval*60))
            queued_topics_len = enque_newest_topics(queued_topics_len)

if __name__ == "__main__":
    main()
