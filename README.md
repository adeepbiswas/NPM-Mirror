# NPM-Mirror

Data pipeline to replicate the NPM Registry using Python, CouchDB, Kafka, Kafka-ui, Prometheus and Grafanan. Meant to be used for research purposes.

# Repository Overview

The data_pipeline/npm-mirror folder contains all the critical files such that the whole pipeline can be run through multiple docker containers using a single command. The files in there are as follows-
  1. app/changes_producer.py - contains the code to read changes from the NPM Registry and add them to a Kafka topic
  2. app/changes_consumer.py - contains the code to consume change messages added to the Kafka stream and process each change by downloading the metadata and tarball corresponding to the change, saving these files in the appropriate directory structure and adding the corresponding record to the mirrored database. The script also produces running logs through various kafka topics.
  3. app/kafka_admin.py - to run Kafka broker and view its metadata
  4. app/latest_seq_ID.txt - read by changes_producer to see where to start reading changes from, based on the NPM API sequence ID. If this file is not present, the changes_producer script starts processing from the current changes that occur once the Python script has started
  5. dbdata - stores the mirrored database files
  6. Dockerfile - contains the configuration to build the Python scripts in the app subdirectory as a docker container image
  7. docker-compose.yml - contains container configuration for running Python scripts, CouchDB, Kafka, Kafka-ui, Prometheus and Grafana
  8. prometheus.yml - contains prometheus configuration
  9. requirements.txt - contains packages needed to run the Python scripts
  10. run_scripts.sh - contains the actual commands that are run in the Python scripts container to run the various Python scripts appropriately.

# Run Configuration

Some important parameters that can be configured in the Python scripts -
  1. LOCAL_PACKAGE_DIR - the path where the files are locally downloaded temporarily for compression
  2. REMOTE_PACKAGE_DIR - the remote file directory path where the compressed files are finally stored
  3. MAX_SIZE - the maximum file such that packages with a size bigger than this are not stored on the server
  4. KAFKA_TOPIC_NUM_PARTITIONS - number of partitions each Kafka topic has
  5. SUBDIRECTORY_HASH_LENGTH - number of characters based on which the packages are hashed while storing in the remote directory in order to have better organization of packages for quicker access from the file system
  6. OLD_PACKAGE_VERSIONS_LIMIT - limits the max number of package versions to be kept in the remote file directory
  7. DATABASE_NAME - the name of the database on the couchdb server under which the changes are recorded

Notes - 
  1. The files are first downloaded and compressed locally first to facilitate faster transfer to the remote directory
  2. If a kafka topic already exists, it's number of partitions won't change by changing the above parameter. The topic would have to be deleted first and then reinitialized for the change to take effect.
# Run Instructions

Move to the directory containing the docker-compose.yml - 
```shell
cd ./data_pipeline/npm-mirror
```

To build / rebuild the docker containers- 
```shell
docker build -t npm-mirror . 
```

To run the containers- 
```shell
docker-compose up
```

To enter terminal for running containers- 
```shell
docker-compose exec -it <container_name> /bin/bash
```

To view container logs- 
```shell
docker-compose logs <container_name>
```

# Reset for Reruns

To delete CouchDB data- 
```shell
sudo rm -rf dbdata
```

To reset kafka broker- 
```shell
docker-compose rm broker-npm
```

# View / Monitor Running Containers

  1. View Database UI- http://127.0.0.1:5984/_utils/
  2. View Kafka-ui - http://localhost:8081/
  3. View Prometheus logs - http://localhost:9091/
  4. View Grafana Dashboard- http://localhost:3001/

Note: Appropriate port forwarding from the server's (VM's) port to the local computer port will be needed to view these on browser
