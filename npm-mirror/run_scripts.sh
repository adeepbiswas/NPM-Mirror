#!/bin/bash

# Run Python scripts one by one
python changes_producer.py
seq 10 | parallel -j 4 python changes_consumer.py
# python changes_producer.py