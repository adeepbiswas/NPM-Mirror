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

LOCAL_PACKAGE_DIR = "temp_packages"
REMOTE_PACKAGE_DIR = "packages"
MAX_SIZE = 5e+6
DB_USER = 'admin'
DB_PASSWORD = 'opensesame123'
DATABASE_NAME = 'test_run_3'

# Create a metric to track time spent and requests made.
REQUEST_TIME = Summary('request_processing_seconds', 'Time spent processing request')
npmUpdateCounter = Counter('npmmirror_npm_update_counter', 'number of npm updates processed')
downloadQueueLength = Gauge('npmmirror_download_queue_length', 'length of the download queue')
lastSeq = Gauge('npmmirror_last_seq_processed', 'value of the last seq processed')
newestSeq = Gauge('npmmirror_newest_seq', 'value of the newest seq on the server')

# Establish Couchdb server connection
server = couchdb.Server('http://{user}:{password}@localhost:5984/'.format(user=DB_USER, password=DB_PASSWORD))

# Function to create or connect to our own CouchDB database
def create_or_connect_db(server, database_name):
    try:
        db = server.create(database_name)
        print(f"Created new database: {database_name}")
    except couchdb.http.PreconditionFailed:
        db = server[database_name]
        print(f"Connected to existing database: {database_name}")
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

    # Create subdirectories based on first character of the package name to add heirarchy
    first_char = package_name[0].upper()
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
            print("--Saved package JSON")  
        if os.path.getsize(doc_path) > MAX_SIZE:
            os.remove(doc_path)
            print("--Package JSON too large, removed")
            saved = False
            doc_path = None

        # Saving the tarball only if the JSON was saved
        if saved:
            # Save the updated (latest) package as a tar file in temporary local directory
            latest = doc['dist-tags']['latest']
            tarball_url = doc['versions'][latest]['dist']['tarball']
            # tarball_url = f"https://registry.npmjs.org/{package_name}/-/{package_name}-{doc['dist-tags']['latest']}.tgz"
            tarball_filename = f"{package_name}_package.tgz"
            tarball_path = os.path.join(package_dir, tarball_filename)
            
            response = requests.get(tarball_url)
            if response.status_code == 200:
                with open(tarball_path, 'wb') as tarball_file:
                    tarball_file.write(response.content)
                print("--Saved Tar file")
                
                if os.path.getsize(tarball_path) > MAX_SIZE:
                    os.remove(tarball_path)
                    print("--Tarball too large, removed")
                    if doc_path:
                        os.remove(doc_path)
                        print("--Corresponding JSON removed as well")
                        doc_path = None
                    saved = False
                    tarball_path = None
            else:
                if doc_path:
                    os.remove(doc_path)
                    print("--Corresponding JSON removed as well")
                    doc_path = None
                saved = False
                tarball_path = None    
                    
            return doc_path, tarball_path
    return None, None

# Function to compress the downloaded JSON and tarball into a zip file and store it in remote directory
def compress_files(raw_package_name, package_name, revision_id, doc_path, tarball_path):
    package_dir = create_directory_structure(raw_package_name)
    compressed_filename = f"{package_name}_{revision_id}.zip"
    zip_path = os.path.join(package_dir, compressed_filename)
    
    with zipfile.ZipFile(zip_path, 'w') as zip_file:
        if doc_path:
            zip_file.write(doc_path, os.path.basename(doc_path))
            os.remove(doc_path)  # Remove the individual JSON file from local (temp) directory after compression
        if tarball_path:
            zip_file.write(tarball_path, os.path.basename(tarball_path))
            os.remove(tarball_path)  # Remove the individual tar file from local (temp) directory after compression
    print("--Compressed zip saved in remote")
    return zip_path

# Function to save the processed change details in our own database
def store_change_details(change, db, zip_path):
    # Store the important details regarding the change in the local CouchDB database.

    package_name = change['id']
    change_seq_id = change['seq']
    package_revision_id = change['doc']['_rev']
    package_latest_version = change['doc']['dist-tags']['latest']
    package_versions_count = len(change['doc']['versions'].keys())
    package_latest_change_time = change['doc']['time'][package_latest_version]
    
    data = {
        'package_name': package_name, 
        'change_seq_id': change_seq_id,
        'package_revision_id': package_revision_id,
        'package_latest_version': package_latest_version,
        'package_versions_count': package_versions_count,
        'package_latest_change_time': package_latest_change_time,
        'change_save_path': zip_path
    }
    db.save(data)
    print("--Change record added to database")

# Main function that reads changes from the NPM Registry and processes them by downloading
# corresponding files and making an entry for the change into our database
# def stream_npm_updates():
#     # access the changes API from Replicate (Public DB Replica for NPM Registry)
#     url = 'https://replicate.npmjs.com/_changes?include_docs=true&feed=continuous&heartbeat=10000&style=all_docs&conflicts=true&since=25318031' #&limit=20'
#     response = requests.get(url, stream=True)
#     if response.status_code != 200:
#         print(f'Error connecting to the CouchDB stream: {response.status_code}')
#         return

#     # Create or connect to our database
#     db = create_or_connect_db(server, DATABASE_NAME)

#     # counter for number of changes read from the stream
#     i = 0

#     for line in response.iter_lines():
#         i += 1
#         # print(i)
#         # print(line)
#         if line:
#             change = json.loads(line)
#             raw_package_name = change['id']
#             print("Change sequence ID: ", change['seq'])
#             print("Raw package name: ", raw_package_name)
#             if "/" in raw_package_name:
#                 segments = raw_package_name.split("/")
#                 package_name = segments[-1]
#             else:
#                 package_name = raw_package_name
            
#             doc_path, tarball_path = download_document_and_package(change, package_name)
            
#             if doc_path:
#                 zip_path = compress_files(raw_package_name, package_name, change['doc']['_rev'], doc_path, tarball_path)
#                 store_change_details(change, db, zip_path)
        # break

# stream_npm_updates()
###

# Initialize a queue to hold the unprocessed changes
change_queue = queue.Queue()

# # Function to process changes from the queue asynchronously
# def process_changes_async(db):  # Pass 'db' as an argument
#     while True:
#         change = change_queue.get()
#         raw_package_name = change['id']
#         print("Change sequence ID: ", change['seq'])
#         print("Raw package name: ", raw_package_name)
#         if "/" in raw_package_name:
#             segments = raw_package_name.split("/")
#             package_name = segments[-1]
#         else:
#             package_name = raw_package_name
        
#         doc_path, tarball_path = download_document_and_package(change, package_name)
        
#         if doc_path:
#             zip_path = compress_files(raw_package_name, package_name, change['doc']['_rev'], doc_path, tarball_path)
#             store_change_details(change, db, zip_path)
#         change_queue.task_done()
###

# Flag to indicate that the streaming has finished
streaming_finished = False

# Function to process a single change
@REQUEST_TIME.time()
def process_change(change):
    raw_package_name = change['id']
    print("Change sequence ID: ", change['seq'])
    print("Raw package name: ", raw_package_name)
    if "/" in raw_package_name:
        segments = raw_package_name.split("/")
        package_name = segments[-1]
    else:
        package_name = raw_package_name
    
    doc_path, tarball_path = download_document_and_package(change, package_name)
    
    if doc_path:
        zip_path = compress_files(raw_package_name, package_name, change['doc']['_rev'], doc_path, tarball_path)
        store_change_details(change, db, zip_path)
    
    npmUpdateCounter.inc()

# Function to process changes from the queue asynchronously using a thread pool
def process_changes_async(db, num_threads=4):  # Pass 'db' as an argument and set the number of threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        while True:
            try:
                change = change_queue.get(timeout=1)  # Wait for 1 second for a change to appear in the queue
            except queue.Empty:
                if streaming_finished:  # Exit the loop if streaming has finished and the queue is empty
                    break
                else:
                    continue
            executor.submit(process_change, change)
            change_queue.task_done()

# Main function that reads changes from the NPM Registry and adds them to the queue
def stream_npm_updates():
    # access the changes API from Replicate (Public DB Replica for NPM Registry)
    url = 'https://replicate.npmjs.com/_changes?include_docs=true&feed=continuous&heartbeat=10000&style=all_docs&conflicts=true&since=25318031' #&limit=20'
    response = requests.get(url, stream=True)
    if response.status_code != 200:
        print(f'Error connecting to the CouchDB stream: {response.status_code}')
        return

    # counter for number of changes read from the stream
    i = 0

    for line in response.iter_lines():
        i += 1
        if line:
            change = json.loads(line)
            change_queue.put(change)  # Put the change into the queue for processing
        # break

if __name__ == '__main__':
    # Start up the server to expose the metrics.
    start_http_server(8000)

    # Create or connect to our database
    db = create_or_connect_db(server, DATABASE_NAME)

    # Start asynchronous processing of changes
    async_process_thread = threading.Thread(target=process_changes_async, args=(db,))  # Pass 'db' as an argument
    async_process_thread.daemon = True
    async_process_thread.start()

    # Start streaming and processing changes
    stream_npm_updates()

    # Indicate that streaming has finished
    streaming_finished = True

    # Wait for the queue to be empty, meaning all changes have been processed
    change_queue.join()
