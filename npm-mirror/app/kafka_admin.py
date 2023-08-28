from confluent_kafka import Consumer, Producer, KafkaError
from changes_producer import streaming_finished
from confluent_kafka.admin import AdminClient, NewTopic

#creating kafka admin client and topics
ac = AdminClient({"bootstrap.servers": "localhost:9092"})

t = ac.list_topics().topics
print(t)