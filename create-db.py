import os
import json
import couchdb
import datetime

# Establish server connection
server = couchdb.Server('http://{user}:{password}@localhost:5984/'.format(user='admin', password='opensesame123'))

# Function to create or connect to the CouchDB database
def create_or_connect_db(server, database_name):
    try:
        db = server.create(database_name)
        print(f"Created new database: {database_name}")
    except couchdb.http.PreconditionFailed:
        db = server[database_name]
        print(f"Connected to existing database: {database_name}")
    return db

#picks the latest json file
def get_latest_file_name(file_names):
    latest_file_name = None
    latest_timestamp = None
    for file_name in file_names:
        timestamp = datetime.datetime.strptime(file_name[:-5], '%Y-%m-%dT%H:%M:%S.%fZ')
        if latest_timestamp is None or timestamp > latest_timestamp:
            latest_file_name = file_name
            latest_timestamp = timestamp
    return latest_file_name

# Function to process a subdirectory
def process_subdirectory(db, subdirectory):
    json_files = []
    tgz_file = None
    for file_name in os.listdir(subdirectory):
        if file_name.endswith('.tgz'):
            tgz_file = file_name
        elif file_name.endswith('.json'):
            json_files.append(file_name)
    
    latest_json_file = get_latest_file_name(json_files)
    json_file_path = os.path.join(subdirectory, latest_json_file)
    if tgz_file != None:
        tgz_file_path = os.path.join(subdirectory, tgz_file)
    else:
        tgz_file_path = None
    
    print(json_file_path)
    print(tgz_file_path)
    print(latest_json_file)

    with open(json_file_path) as json_file:
        data = json.load(json_file)
        data['tgz_file_path'] = tgz_file_path # if os.path.exists(tgz_file_path) else None
        print(data.keys())
        #data = data['_id', '_rev', 'name', 'dist-tags', 'versions', 'time']
        selected_data = {key: data[key] for key in ['_id', '_rev', 'name']}
        data = {'type': 'Person', 'name': 'John Doe'}
        print(selected_data)
        print(data)
        db.save(selected_data)

    print(f"Processed record: {subdirectory} saved")

# Directory path
directory_path = './toy-data'

# Database name
database_name = 'toy-db'

# Create or connect to the database
db = create_or_connect_db(server, database_name)

# Traverse through subdirectories
for subdir in os.listdir(directory_path):
    subdirectory = os.path.join(directory_path, subdir)
    print(subdirectory)
    if os.path.isdir(subdirectory):
        process_subdirectory(db, subdirectory)
