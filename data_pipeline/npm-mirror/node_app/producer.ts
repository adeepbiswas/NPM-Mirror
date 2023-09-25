import ChangesStream from 'changes-stream';
import { writeFile, mkdir, access, unlink } from 'node:fs/promises';
import { createWriteStream, writeFileSync, readFileSync } from 'node:fs';
import { Writable } from 'node:stream';
import * as path from 'path';
import normalize from 'normalize-registry-metadata'
import Queue from 'better-queue'
import { Counter, Gauge, collectDefaultMetrics, register } from 'prom-client'
import express from 'express';
import https from 'https';
import bent from 'bent'
import { Kafka, KafkaConfig } from 'kafkajs';
const { CompressionTypes } = require('kafkajs')

//kafka 
const kafkaConfig: KafkaConfig = { brokers: ['broker-npm:9092'] }
const kafka = new Kafka(kafkaConfig)

const producer = kafka.producer();
const admin = kafka.admin();

async function createTopicIfNotExists(topicName: string) {
    try {
        await admin.connect();

        const topic = await admin.listTopics();
        if (!topic.includes(topicName)) {
        const topicConfig = {
            topic: topicName,
            numPartitions: 12,
            replicationFactor: 1,
        };

        await admin.createTopics({
            topics: [topicConfig],
        });

        console.log(`Topic "${topicName}" created successfully`);
        } else {
        console.log(`Topic "${topicName}" already exists`);
        }
    } catch (error) {
        console.error('Error creating/checking topic:', error);
    } finally {
        await admin.disconnect();
    }
}
const topicName = 'npm-changes'; 
createTopicIfNotExists(topicName);
const topicName2 = 'run_logs'; 
createTopicIfNotExists(topicName2);
const topicName3 = 'skipped_changes'; 
createTopicIfNotExists(topicName3);

// initializing
import config from './config.json';
try {
    const seq_store = JSON.parse(readFileSync(config.update_seq_store).toString())
    console.log("Stored seq - ", seq_store.update_seq)
    if (seq_store && seq_store.update_seq) { // && (seq_store.update_seq > config.update_seq)) {
        console.log(`Starting with stored ${seq_store.update_seq} rather than config's ${config.update_seq} seq`)
        config.update_seq = seq_store.update_seq
    }
} catch (e) { }
console.log(`Tracking changes to ${config.couchdb} from ${config.update_seq}`)

// metrics / monitoring
let npmUpdateCounter = new Counter({ name: "npmmirror_npm_update_counter", help: "number of npm updates processed" })
let downloadQueueLength = new Gauge({ name: "npmmirror_download_queue_length", help: "length of the download queue" })
let lastSeq = new Gauge({ name: "npmmirror_last_seq_processed", help: "value of the last seq processed" })
let newestSeq = new Gauge({ name: "npmmirror_newest_seq", help: "value of the newest seq on the server" })
collectDefaultMetrics({ prefix: "npmmirror_" })
let app = express()
app.get('/metrics', async (req, res) => {
    try {
        res.set('Content-Type', register.contentType);
        res.end(await register.metrics());
    } catch (ex) {
        res.status(500).end(ex);
    }
});
app.listen(8084, () => console.log(`Metrics listening on port 8084.`));


// subscribing to npm changes
var changes = new ChangesStream({
    db: config.couchdb,
    include_docs: true,
    since: config.update_seq
});

let changeProcessor = new Writable({
    objectMode: true,
    write: async function(change, ignore, cb) {
        npmUpdateCounter.inc()
        if (change && change.seq) lastSeq.set(change.seq)

        normalize(change)

        console.log("sending change to kafka");
        produceMessages(topicName, JSON.stringify(change), change.seq, change.id);
  
        // keeping last processed id
        await writeFile(config.update_seq_store, `{"update_seq":${change.seq}}`)
        cb()
    }
})
changes.pipe(changeProcessor)

changes.on('error', function (e) {
    console.log(e);
});

function pkgDir(pkgId: string) {
    return path.join(config.targetDir, pkgId)
}

async function produceMessages(topicName: string, message, change_seq, change_id) {
    try {
        await producer.connect();
    
        await producer.send({
            topic: topicName,
            compression: CompressionTypes.GZIP,
            messages : [{
                key: String(change_seq),
                value: message}],
        });
    
        console.log('Change added successfully - ', change_seq);
    } catch (error) {
        console.error('Change message too large, skipped :', change_seq);
        await producer.send({
            topic: topicName3,
            messages : [{
                value: JSON.stringify({ 'Change Seq ID': String(change_seq), 'Package Name': String(change_id) })
            }],
        });
    } finally {
        await producer.disconnect();
    }
}

//once ever 5 min check the newest seq number of the database to see how far we are behind
const getJSON = bent('json')
async function checkNewestSeq() {
    try {
        const r = await getJSON(config.couchdb)
        if (r && r.update_seq) {
            console.log("---- latest seq on NPM Registry: "+r.update_seq)
            newestSeq.set(r.update_seq)
        }
    } catch (e) {}
    setTimeout(checkNewestSeq, 1000)
}
checkNewestSeq()