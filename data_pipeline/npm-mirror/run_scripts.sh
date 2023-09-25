#!/bin/bash

# Run Python scripts one by one
sleep 20 #to wait for kafka broker and couchserver to be up and running
ts-node ./node_app/producer.ts &
# python -u ./app/changes_producer.py &
seq 4 | parallel --linebuffer -j 4 python -u ./app/changes_consumer.py &
wait
# python changes_producer.py