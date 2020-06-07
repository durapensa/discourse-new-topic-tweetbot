# discourse-new-topic-tweetbot

Intended to run as a daemon on the host running Discourse, the bot
polls Discourse's latest topics (latest.json) then tweets new topics matching
your criteria to your registered Twitter feed (see Customizations, below). 

Tweets may include a topic thumbnail image, if one exists, Twitter hashtags,
and Twitter mentions, if those exist. 
(see Twitter's automation rules at https://help.twitter.com/en/rules-and-policies/twitter-automation#replies-mentions).

## Installation

The file `settings.ini`, or environment variables,  must be populated with
keys from both Discourse and Twitter. Instructions for creating Twitter keys
can be found at
https://realpython.com/twitter-bot-python-tweepy/#creating-twitter-api-authentication-credentials.
Create a Discourse single-user key at ☰ > Settings > API > New API Key.

Valid setup & desired customizations can be tested before installation. 
At the command line, running `python3 discourse-new-topic-tweetbot.py` should
output the tweet-fomrated text of the current most newly created topic, along with
the system path of its thumbnail image, if one exists.

The recommended installation method is `sudo pip3 install -r requirements.txt`
followd by `sudo install discourse_new_topic_tweetbot.py /usr/local/bin`. 
Of course running from a user's local python packages or venv works as well.
It is left to the user to manage running `discourse_new_topic_tweetbot.py`
as a daemon (docker, systemd, cron, etc.)

If installed on a different host from the Discourse instance, the bot must be
customized to download topic thumbnail images, if those are desired.

To use the included Dockerfile, all required settings from `settings.ini` 
must be passed to `docker run` using environment variables, e.g. 
`sudo docker build . -t bot`
followd by
`sudo docker run -it --env-file settings.ini --entrypoint sh bot`
to test settings, and 
`sudo docker run -d --env-file settings.ini bot` to run as a daemon. To access
the Discourse server's images, add a bind mount, e.g. 
`-v /var/discourse/shared/standalone:/var/discourse/shared/standalone`

## Settings & Customization

The file `settings.ini` contains authentication credentials and settings.

At startup, if no NEW topics are among `latest.json` (a 30-item-long list), the
bot will tweet the NEWEST among them. This may be addressed by assigning a
value to `DISCOURSE_NEWEST_TOPIC_ID`. Changing this value can also prevent the
bot from creating a duplicate tweet in the case of a manual restart.

The default `POLLING_INTERVAL` is 10 minutes, and this also serves as a delay
for fetching thumbnails, as Discourse thumbnail generation is rate-limited.

`TWEET_STRING` `TWEET_HASHTAGS` `TWEET_MENTIONS` will be added to the beginning
of each tweet.

Inclusion of thumbnail media in tweets may be disabled by setting 
`TWEET_THUMBNAILS` to `None` or `0`.

Further customizations may be made in `discourse-new-topic-tweetbot.py`. Some
of the best candidates are the `build_tweet_string()` fuction and the 
`FindTwitterMentions` class.

## Credits & Attributions

Thanks to the develoeprs of Discourse https://www.discourse.org/ and the 
outstanding Discourse community. 

Thanks to the developers of the Discourse & Twitter libraries used, and others:

https://pypi.org/project/discourse/

https://pypi.org/project/tweepy/

https://pypi.org/project/python-decouple/ 
