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
from changes_producer import streaming_finished
from confluent_kafka.admin import AdminClient, NewTopic
from dotenv import load_dotenv

LOCAL_PACKAGE_DIR = "temp_packages"
REMOTE_PACKAGE_DIR = "packages"
MAX_SIZE = 10e+6
DATABASE_NAME = 'npm-mirror'
KAFKA_TOPIC_NUM_PARTITIONS = 12
KAFKA_TOPIC_REPLICATION_FACTOR = 1
SUBDIRECTORY_HASH_LENGTH = 3
OLD_PACKAGE_VERSIONS_LIMIT = 3 #determines max how many package versions to keep

# Specify the path to the .env file in the main directory
dotenv_path = '.env'
# Load environment variables from the .env file
load_dotenv(dotenv_path)

# Access the variables
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Create prmethius metrics to track time spent and requests made.
REQUEST_TIME = Summary('request_processing_seconds', 'Time spent processing request')
npmUpdateCounter = Counter('npmmirror_npm_update_counter', 'number of npm updates processed')
downloadQueueLength = Gauge('npmmirror_download_queue_length', 'length of the download queue')
lastSeq = Gauge('npmmirror_last_seq_processed', 'value of the last seq processed')
newestSeq = Gauge('npmmirror_newest_seq', 'value of the newest seq on the server')

# Establish Couchdb server connection
server = couchdb.Server('http://{user}:{password}@couchserver:5984/'.format(user=DB_USER, password=DB_PASSWORD))

# Initialize a lock for accessing shared resources
shared_resource_lock = threading.Lock()

#creating kafka admin client and topics
ac = AdminClient({"bootstrap.servers": "broker-npm:9092"})
 
topic1 = NewTopic('downloaded_in_local', num_partitions=KAFKA_TOPIC_NUM_PARTITIONS, replication_factor=KAFKA_TOPIC_REPLICATION_FACTOR)
topic2 = NewTopic('moved_to_remote', num_partitions=KAFKA_TOPIC_NUM_PARTITIONS, replication_factor=KAFKA_TOPIC_REPLICATION_FACTOR)
topic3 = NewTopic('added_to_db', num_partitions=KAFKA_TOPIC_NUM_PARTITIONS, replication_factor=KAFKA_TOPIC_REPLICATION_FACTOR)
topic4 = NewTopic('run_logs', num_partitions=KAFKA_TOPIC_NUM_PARTITIONS, replication_factor=KAFKA_TOPIC_REPLICATION_FACTOR)
topic5 = NewTopic('skipped_changes', num_partitions=KAFKA_TOPIC_NUM_PARTITIONS, replication_factor=KAFKA_TOPIC_REPLICATION_FACTOR)

fs = ac.create_topics([topic1, topic2, topic3, topic4, topic5])

# Initialize Kafka producer
kafka_producer = Producer({"bootstrap.servers": "broker-npm:9092"})

kafka_consumer = Consumer({
    "bootstrap.servers": "broker-npm:9092",
    "group.id": "npm-update-group",
    "auto.offset.reset": "earliest",
    "max.partition.fetch.bytes": 10485760  # 10 MB in bytes
})
kafka_consumer.subscribe(["npm-changes"])

# Function to create or connect to our own CouchDB database
def create_or_connect_db(server, database_name):
    try:
        db = server.create(database_name)
        log_message = f"Created new database: {database_name}"
        print(log_message)
        kafka_producer.produce("run_logs", value=log_message)
        kafka_producer.flush()
    except couchdb.http.PreconditionFailed:
        db = server[database_name]
        log_message = f"Connected to existing database: {database_name}"
        print(log_message)
        kafka_producer.produce("run_logs", value=log_message)
        kafka_producer.flush()
    return db

# Function to remove special characters from package names
def remove_special_characters(input_string):
    pattern = r"[^a-zA-Z0-9/]"
    cleaned_string = re.sub(pattern, "", input_string)
    return cleaned_string

# Function to create temporary local directory and organized remote (NAS) directory structure
def create_directory_structure(package_name):
    #Create parent directory in local and remote storage system
    if not os.path.exists(REMOTE_PACKAGE_DIR):
        os.mkdir(REMOTE_PACKAGE_DIR)
    if not os.path.exists(LOCAL_PACKAGE_DIR):
        os.mkdir(LOCAL_PACKAGE_DIR)

    # Create subdirectories based on first 3 characters of the package name to add heirarchy
    if len(package_name) >= SUBDIRECTORY_HASH_LENGTH:
        first_char = package_name[0:SUBDIRECTORY_HASH_LENGTH].upper()
    else:
        first_char = package_name[0].upper()
    # first_char = package_name[0].upper()
    alpha_dir = os.path.join(REMOTE_PACKAGE_DIR, first_char)
    if not os.path.exists(alpha_dir):
        os.mkdir(alpha_dir)

    # Create subdirectory for each package in the corresponding alphabet directory
    if '/' in package_name:
        package_dir = alpha_dir
        segments = package_name.split("/")
        for segment in segments:
            package_dir = os.path.join(package_dir, segment)
            if not os.path.exists(package_dir):
                os.mkdir(package_dir)
    else:
        package_dir = os.path.join(alpha_dir, package_name)
        if not os.path.exists(package_dir):
            os.mkdir(package_dir)

    return package_dir

# Function to download package JSON and tarball corresponding to each change
def download_document_and_package(change, package_name):
    doc = change.get('doc')
    if doc:
        # creating directory in local storage for temporary downlaod and compression 
        # before moving to remote directory (for faster transfers)
        package_dir = LOCAL_PACKAGE_DIR
        if not os.path.exists(LOCAL_PACKAGE_DIR):
            os.mkdir(LOCAL_PACKAGE_DIR)
        
        saved = True

        # Save the document as a JSON file in temporary local directory
        doc_filename = f"{package_name}_doc.json"
        doc_path = os.path.join(package_dir, doc_filename)
        
        with open(doc_path, 'w') as doc_file:
            json.dump(doc, doc_file)
            log_message = "--Saved package JSON"
            print(log_message)  
            kafka_producer.produce("run_logs", value=log_message)
            kafka_producer.flush()
        if os.path.getsize(doc_path) > MAX_SIZE:
            os.remove(doc_path)
            log_message = "--Package JSON too large, removed"
            print(log_message)
            kafka_producer.produce("run_logs", value=log_message)
            kafka_producer.flush()
            saved = False
            doc_path = None

        # Saving the tarball only if the JSON was saved
        if saved:
            # Save the updated (latest) package as a tar file in temporary local directory
            latest = doc['dist-tags']['latest']
            tarball_url = doc['versions'][latest]['dist']['tarball']
            tarball_filename = f"{package_name}_package.tgz"
            tarball_path = os.path.join(package_dir, tarball_filename)
            
            response = requests.get(tarball_url)
            if response.status_code == 200:
                with open(tarball_path, 'wb') as tarball_file:
                    tarball_file.write(response.content)
                log_message = "--Saved Tar file"
                print(log_message)
                kafka_producer.produce("run_logs", value=log_message)
                kafka_producer.flush()
                
                if os.path.getsize(tarball_path) > MAX_SIZE:
                    os.remove(tarball_path)
                    log_message = "--Tarball too large, removed"
                    print(log_message)
                    kafka_producer.produce("run_logs", value=log_message)
                    kafka_producer.flush()
                    if doc_path:
                        os.remove(doc_path)
                        log_message = "--Corresponding JSON removed as well"
                        print(log_message)
                        kafka_producer.produce("run_logs", value=log_message)
                        kafka_producer.flush()
                        doc_path = None
                    saved = False
                    tarball_path = None
            else:
                if doc_path:
                    os.remove(doc_path)
                    log_message = "--Corresponding JSON removed as well"
                    print(log_message)
                    kafka_producer.produce("run_logs", value=log_message)
                    kafka_producer.flush()
                    doc_path = None
                saved = False
                tarball_path = None    
                    
            return doc_path, tarball_path
    return None, None

def get_zip_creation_time(zip_filename):
    # Get the creation time of the zip file
    zip_creation_time = os.path.getctime(zip_filename)
    return zip_creation_time

#deletes the oldest zip version if there are already 3 or more versions present
def delete_oldest_zip(directory):
    zip_files = [file for file in os.listdir(directory) if file.lower().endswith('.zip')]

    if len(zip_files) >= OLD_PACKAGE_VERSIONS_LIMIT:
        zip_file_times = [(zip_file, get_zip_creation_time(os.path.join(directory, zip_file))) for zip_file in zip_files]
        oldest_zip = min(zip_file_times, key=lambda x: x[1])[0]
        
        oldest_zip_path = os.path.join(directory, oldest_zip)
        os.remove(oldest_zip_path)
        log_message = f"Deleted the oldest zip file: {oldest_zip}"
        print(log_message)
        kafka_producer.produce("run_logs", value=log_message)
        kafka_producer.flush()

# Function to compress the downloaded JSON and tarball into a zip file and store it in remote directory
def compress_files(raw_package_name, package_name, revision_id, doc_path, tarball_path):
    package_dir = create_directory_structure(raw_package_name)
    delete_oldest_zip(package_dir)
    compressed_filename = f"{package_name}_{revision_id}.zip"
    zip_path = os.path.join(package_dir, compressed_filename)
    
    with zipfile.ZipFile(zip_path, 'w') as zip_file:
        if doc_path:
            zip_file.write(doc_path, os.path.basename(doc_path))
            os.remove(doc_path)  # Remove the individual JSON file from local (temp) directory after compression
        if tarball_path:
            zip_file.write(tarball_path, os.path.basename(tarball_path))
            os.remove(tarball_path)  # Remove the individual tar file from local (temp) directory after compression
    log_message = "--Compressed zip saved in remote"
    print(log_message)
    kafka_producer.produce("run_logs", value=log_message)
    kafka_producer.flush()
    
    return zip_path

# Function to save the processed change details in our own database
def store_change_details(change, db, zip_path):
    # Store the important details regarding the change in the local CouchDB database.
    package_name = change['id']
    change_seq_id = change['seq']
    package_revision_id = change['doc']['_rev']
    package_latest_version = change['doc']['dist-tags']['latest']
    package_versions_count = len(change['doc']['versions'].keys())
    
    package_latest_authors = None
    package_latest_maintainers = None
    package_latest_dependencies = None
    if 'author' in change['doc']['versions'][package_latest_version].keys():
        package_latest_authors = change['doc']['versions'][package_latest_version]['author']
    if 'maintainers' in change['doc']['versions'][package_latest_version].keys():
    package_latest_maintainers = change['doc']['versions'][package_latest_version]['maintainers']
    if 'dependencies' in change['doc']['versions'][package_latest_version].keys():
    package_latest_dependencies = change['doc']['versions'][package_latest_version]['dependencies']
    
    package_modification_count = len(change['doc']['time'].keys())
    package_latest_change_time = change['doc']['time'][package_latest_version]
    package_distribution_tags = change['doc']['dist-tags']
    
    package_deleted = False
    change_keys = list(change.keys())
    if 'deleted' in change_keys:
        package_deleted = change['deleted']
    
    data = {
        'package_name': package_name, 
        'change_seq_id': change_seq_id,
        'package_revision_id': package_revision_id,
        'package_latest_version': package_latest_version,
        'package_versions_count': package_versions_count,
        'package_modification_count': package_modification_count,
        'package_latest_change_time': package_latest_change_time,
        'package_latest_authors': package_latest_authors,
        'package_latest_maintainers': package_latest_maintainers,
        'package_latest_dependencies': package_latest_dependencies,
        'change_save_path': zip_path,
        'package_deleted' : package_deleted,
        'package_distribution_tags': package_distribution_tags
    }
    db.save(data)
    log_message = "--Change record added to database"
    print(log_message)
    kafka_producer.produce("run_logs", value=log_message)
    kafka_producer.flush()

# Function to process a single change
@REQUEST_TIME.time()
def process_change(db, change):
    raw_package_name = change['id']
    
    log_message = f"Change sequence ID: {change['seq']}"
    print(log_message)
    kafka_producer.produce("run_logs", value=log_message)
    kafka_producer.flush()
    log_message = f"Raw package name: {raw_package_name}"
    print(log_message)
    kafka_producer.produce("run_logs", value=log_message)
    kafka_producer.flush()
    
    if "/" in raw_package_name:
        segments = raw_package_name.split("/")
        package_name = segments[-1]
    else:
        package_name = raw_package_name
    
    doc_path, tarball_path = download_document_and_package(change, package_name)
    # add to download queue
    # kafka_producer.produce("downloaded_in_local", value=change['seq'])
    kafka_producer.produce("downloaded_in_local", str(change['seq']))
    kafka_producer.flush()
    
    if doc_path:
        zip_path = compress_files(raw_package_name, package_name, change['doc']['_rev'], doc_path, tarball_path)
        # add to moved to remote queue
        kafka_producer.produce("moved_to_remote", value=str(change['seq']))
        kafka_producer.flush()
        store_change_details(change, db, zip_path)
        # add to recorded in db queue
        kafka_producer.produce("added_to_db", value=str(change['seq']))
        kafka_producer.flush()
    else:
        kafka_producer.produce("skipped_changes", value=str(change['seq']))
        kafka_producer.flush()
    
    npmUpdateCounter.inc()

# Function to process changes from Kafka stream asynchronously using a thread pool
def process_changes_async(db):  
    # with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
    while True:
        msg = kafka_consumer.poll(1.0)  # Poll Kafka stream for messages
        
        if msg is None:  # Continue if no message received
            if streaming_finished:  # Exit the loop if streaming has finished
                log_message = "Stream empty and streaming finished."
                print(log_message)
                kafka_producer.produce("run_logs", value=log_message)
                kafka_producer.flush()
                break
            log_message = "Stream empty."
            # print(log_message)
            # kafka_producer.produce("run_logs", value=log_message)
            # kafka_producer.flush()
            continue
        
        change = json.loads(msg.value())
        
        try:
            process_change(db, change)
            log_message = "Change from kafka stream processed."
            print(log_message)
            kafka_producer.produce("run_logs", value=log_message)
            kafka_producer.flush()
        except Exception as e:
            log_message = f"Error:{e}, skipped change"
            print(log_message)
            kafka_producer.produce("run_logs", value=log_message)
            kafka_producer.flush()
            kafka_producer.produce("skipped_changes", value=str(change['seq']))
            kafka_producer.flush()
    
        # with shared_resource_lock:
        kafka_consumer.commit(msg)

if __name__ == '__main__':
    # Start up the server to expose the metrics.
    # start_http_server(8000)

    # Create or connect to our database
    users_db = create_or_connect_db(server, '_users')
    replicator_db = create_or_connect_db(server, '_replicator')
    db = create_or_connect_db(server, DATABASE_NAME)

    # Start asynchronous processing of changes
    process_changes_async(db)
    # async_process_thread = threading.Thread(target=process_changes_async, args=(db,))  # Pass 'db' as an argument
    # async_process_thread.daemon = True
    # async_process_thread.start()