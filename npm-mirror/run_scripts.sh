#!/bin/bash

# Run Python scripts one by one
sleep 10
python -u ./app/changes_producer.py
# seq 4 | parallel -j 4 python ./app/changes_consumer.py
# python changes_producer.py