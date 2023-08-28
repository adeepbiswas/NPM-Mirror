#!/bin/bash

# Run Python scripts one by one
python ./app/changes_producer.py
seq 4 | parallel -j 4 ./app/python changes_consumer.py
# python changes_producer.py