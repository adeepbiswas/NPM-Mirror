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
SEQ_ID_FILE_NAME = "./app/latest_seq_ID.txt"

# Flag to indicate that the streaming has finished
streaming_finished = False

print("Trying to connect to kafka.")

#creating kafka admin client and topics
ac = AdminClient({"bootstrap.servers": "broker-npm:9092"})
print("kafka connection successful")
 
topic1 = NewTopic('npm-changes', num_partitions=KAFKA_TOPIC_NUM_PARTITIONS, replication_factor=KAFKA_TOPIC_REPLICATION_FACTOR)
topic2 = NewTopic('skipped_changes', num_partitions=KAFKA_TOPIC_NUM_PARTITIONS, replication_factor=KAFKA_TOPIC_REPLICATION_FACTOR)
topic3 = NewTopic('run_logs', num_partitions=KAFKA_TOPIC_NUM_PARTITIONS, replication_factor=KAFKA_TOPIC_REPLICATION_FACTOR)
fs = ac.create_topics([topic1, topic2, topic3])

# Initialize Kafka producer
kafka_producer = Producer({"bootstrap.servers": "broker-npm:9092"})

#stores the last seq ID read from the NPM API 
def write_latest_seq_id_to_file(filename, variable):
    with open(filename, "w") as file:
        file.write(str(variable))

#reads the last seq ID stored 
def read_latest_seq_id_from_file(filename, default_value="now"):
    try:
        with open(filename, "r") as file:
            content = file.read()
            if content:
                return content.strip()
            else:
                return default_value
    except FileNotFoundError:
        return default_value

# function that reads changes from NPM changes API stream and adds them to kafka stream
def stream_npm_updates():
    seq_id = read_latest_seq_id_from_file(SEQ_ID_FILE_NAME)
    url = f'https://replicate.npmjs.com/_changes?include_docs=true&feed=continuous&heartbeat=10000&style=all_docs&conflicts=true&since={seq_id}'
    print("Starting from Seq ID - ", seq_id)
    response = requests.get(url, stream=True)
    
    if response.status_code != 200:
        print(f'Error connecting to the CouchDB stream: {response.status_code}')
        return
    
    for line in response.iter_lines():
        if line:
            change = json.loads(line)
                
            try:
                kafka_producer.produce("npm-changes", value=line)
                kafka_producer.flush()
                print("Change sent to Kafka stream")
                write_latest_seq_id_to_file(SEQ_ID_FILE_NAME, change['seq'])
            except Exception as e:
                if "Message size too large" in str(e) or \
                   "MSG_SIZE_TOO_LARGE" in str(e):
                    log_message = f"Seq ID - {change['seq']} - Message size too large. Unable to produce message."
                    print(log_message)
                    kafka_producer.produce("run_logs", value=log_message)
                else:
                    log_message = f"Seq ID - {change['seq']} - Error:{e}, change skipped."
                    print(log_message)
                    kafka_producer.produce("run_logs", value=log_message)
                kafka_producer.produce("skipped_changes", value=str(change['seq']))
            # except KafkaError as e:
            #     if e.args[0].code() == KafkaError.MSG_SIZE_TOO_LARGE:
            #         print("Message size too large. Unable to produce message.")
            
if __name__ == '__main__':
    # Start up the server to expose the metrics.
    # start_http_server(8000)
    
    stream_npm_updates()
    streaming_finished = True
    print("Streaming finished - ", streaming_finished)