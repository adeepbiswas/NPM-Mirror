# NPM-Mirror

Data pipeline to replicate the NPM Registry using Python, CouchDB, Kafka, Kafka-ui, Prometheus and Grafanan. Meant to be used for research purposes.

# Repository Overview

The data_pipeline/npm-mirror folder contains all the critical files such that the whole pipeline can be run through multiple docker containers using a single command. The files in there are as follows-
  1. node_app/producer.ts - contains the code to read changes from the NPM Registry and add them to a Kafka topic
  2. app/changes_consumer.py - contains the code to consume change messages added to the Kafka stream and process each change by downloading the metadata and tarball corresponding to the change, saving these files in the appropriate directory structure and adding the corresponding record to the mirrored database. The script also produces running logs through various kafka topics.
  3. app/kafka_admin.py - to run Kafka broker and view its metadata
  4. node_app/config.json - read by producer to see where to start reading changes from, based on the NPM API sequence ID. This seq ID is read only if the Kafka topic 'npm-changes' is empty.If 'npm-changes' is not empty, producer starts from the seq ID of the last message stored in the 'npm-changes' topic.
  5. dbdata - stores the mirrored database files
  6. Dockerfile - contains the configuration to build the Python scripts in the app subdirectory as a docker container image
  7. docker-compose.yml - contains container configuration for running Python scripts, CouchDB, Kafka, Kafka-ui, Prometheus and Grafana
  8. prometheus.yml - contains prometheus configuration
  9. requirements.txt - contains packages needed to run the Python scripts
  10. run_scripts.sh - contains the actual commands that are run in the Python scripts container to run the various Python scripts appropriately.
  11. update_seq/* - stores the seq ID of the last message processed along with the full last message json

# Run Configuration

Some important parameters that can be configured in the Python scripts -
  1. LOCAL_PACKAGE_DIR - the path where the files are locally downloaded temporarily for compression
  2. REMOTE_PACKAGE_DIR - the remote file directory path where the compressed files are finally stored
  3. MAX_SIZE - the maximum file such that packages with a size bigger than this are not stored on the server
  4. KAFKA_TOPIC_NUM_PARTITIONS - number of partitions each Kafka topic has
  5. SUBDIRECTORY_HASH_LENGTH - number of characters based on which the packages are hashed while storing in the remote directory in order to have better organization of packages for quicker access from the file system
  6. OLD_PACKAGE_VERSIONS_LIMIT - limits the max number of package versions to be kept in the remote file directory
  7. DATABASE_NAME - the name of the database on the couchdb server under which the changes are recorded
  8. config.json/update_seq - stores the seq ID from which the producer will start if 'npm-changes' is empty. Set to 'now' if the producer has to be started from the latest seq ID or else set to any specific seq ID as a string

Notes - 
  1. The files are first downloaded and compressed locally first to facilitate faster transfer to the remote directory
  2. If a kafka topic already exists, it's number of partitions won't change by changing the above parameter. The topic would have to be deleted first and then reinitialized for the change to take effect.
# Run Instructions

Move to the directory containing the docker-compose.yml - 
```shell
cd /home/adeepb/data_pipeline/NPM-Mirror/data_pipeline/npm-mirror
```

To build / rebuild the docker containers- 
```shell
docker build -t npm-mirror . 
```

To attach to tmux session- 
```shell
tmux attach -t npm-mirror-run
```

To run the containers- 
```shell
docker-compose up --quiet-pull
```

To detach from tmux session- 
```shell
Control + B followed by D
```

To enter terminal for running container- 
```shell
docker exec -it npm-mirror_npm-mirror_1 /bin/bash
```

To view container logs- 
```shell
docker-compose logs npm-mirror
```

# Reset for Reruns

To delete CouchDB data- 
```shell
cd /home/adeepb/data_pipeline/NPM-Mirror/data_pipeline/npm-mirror
sudo rm -rf dbdata
mkdir dbdata
```

To delete downloaded packages / jsons- 
```shell
cd /NPM
sudo rm -rf npm-packages
mkdir npm-packages
```

To reset kafka broker- 
```shell
docker-compose rm broker-npm
```

To reset zookeeper- 
```shell
docker-compose rm zookeeper-npm
```

To reset producer / consumer- 
```shell
docker-compose rm npm-mirror
```

Note - check the config parameters before running specially config.json/update_seq

# Pause and Restart

To attach to tmux session- 
```shell
tmux attach -t npm-mirror-run
```

Control + C to stop all running containers (make sure to be in the npm-mirror directory where the docker-compose file is present)

To restart the containers- 
```shell
docker-compose up --quiet-pull
```

To detach from tmux session- 
```shell
Control + B followed by D
```

# Producer Restart Logic

Sometimes the Kafka producer might get disconnected from the NPM API and stop reading new changes after having made too many requests. In such a case, the producer automatically gets restarted if the lag between the last seq ID sent to kafka broker and the last seq ID in the NPM grows by more than 200 from the initial lag.

To check initial lag- 
```shell
cd /home/adeepb/data_pipeline/NPM-Mirror/data_pipeline/npm-mirror
docker-compose logs npm-mirror | grep 'Lag' | awk '{print}'
```

# View / Monitor Running Containers

  1. View Database UI- http://127.0.0.1:5984/_utils/
  2. View Kafka-ui - http://localhost:8081/
  3. View Prometheus - http://feature.isri.cmu.edu:9090/targets?search=
  4. View Grafana Dashboard- http://localhost:3001/

Note: Appropriate port forwarding from the server's (VM's) port to the local computer port will be needed to view these on browser
