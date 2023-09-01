# NPM-Mirror

Data pipeline to replicate the NPM Registry using Python, CouchDB, Kafka, Kafka-ui, Prometheus and Grafanan. Meant to be used for research purposes.

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
