FROM python:3.8-alpine

COPY requirements.txt /tmp
RUN pip3 install -r /tmp/requirements.txt
COPY discourse_new_topic_tweetbot.py /

WORKDIR /
ENTRYPOINT ["python3"]
CMD ["/discourse_new_topic_tweetbot.py"]
