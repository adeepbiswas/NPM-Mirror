#!/bin/bash

# Run Python scripts one by one
sleep 30 #to wait for kafka broker and couchserver to be up and running
# ts-node ./node_app/producer.ts &
# python -u ./app/changes_producer.py &
while true; do
  echo "Starting / Restarting producer script..."
  # Run kcat with a timeout of 5 seconds to prevent it from waiting indefinitely
  timeout 5 kcat -C -b broker-npm:9092 -t npm-changes -o -1 -c 1 > ./update_seq/kafka_last_message.json
  kcat_exit_code=$?
  echo "exit code - $kcat_exit_code"
  # Check if kcat was successful or timed out
  if [ $kcat_exit_code -eq 124 ]; then
    echo "kcat timed out, empty topc. Proceeding with the script."
  else
    echo "kcat completed successfully."
  fi
  ts-node ./node_app/producer.ts # "$last_message"
done &
seq 4 | parallel --linebuffer -j 4 python -u ./app/changes_consumer.py &
wait
# python changes_producer.py