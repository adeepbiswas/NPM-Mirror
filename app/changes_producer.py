import os
import requests
import json
import tarfile
import zipfile
import re
import couchdb
import datetime
import queue
import threading
import concurrent.futures
from prometheus_client import start_http_server, Summary, Counter, Gauge
from confluent_kafka import Consumer, Producer, KafkaError
from confluent_kafka.admin import AdminClient, NewTopic

KAFKA_TOPIC_NUM_PARTITIONS = 4
KAFKA_TOPIC_REPLICATION_FACTOR = 1

# Flag to indicate that the streaming has finished
streaming_finished = False

#creating kafka admin client and topics
ac = AdminClient({"bootstrap.servers": "localhost:9092"})
 
topic = NewTopic('npm-changes', num_partitions=KAFKA_TOPIC_NUM_PARTITIONS, replication_factor=KAFKA_TOPIC_REPLICATION_FACTOR)
fs = ac.create_topics([topic])

# Initialize Kafka producer
kafka_producer = Producer({"bootstrap.servers": "localhost:9092"})

# function that reads changes from NPM changes API stream and adds them to kafka stream
def stream_npm_updates():
    url = 'https://replicate.npmjs.com/_changes?include_docs=true&feed=continuous&heartbeat=10000&style=all_docs&conflicts=true&since=25318031'
    response = requests.get(url, stream=True)
    
    if response.status_code != 200:
        print(f'Error connecting to the CouchDB stream: {response.status_code}')
        return
    
    for line in response.iter_lines():
        if line:
            try:
                kafka_producer.produce("npm-changes", value=line)
                kafka_producer.flush()
                print("Change sent to Kafka stream")
            except Exception as e:
                if "Message size too large" in str(e) or \
                   "MSG_SIZE_TOO_LARGE" in str(e):
                    print("Message size too large. Unable to produce message.")
                else:
                    print("Error:", e)
            # except KafkaError as e:
            #     if e.args[0].code() == KafkaError.MSG_SIZE_TOO_LARGE:
            #         print("Message size too large. Unable to produce message.")
            
if __name__ == '__main__':
    stream_npm_updates()
    streaming_finished = True
    print("Streaming finished - ", streaming_finished)