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
    if (seq_store && seq_store.update_seq && (seq_store.update_seq > config.update_seq)) {
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
        // produceMessages(topicName, change);

        // var promise
        // if (change.deleted) {
        //     await writeDeletion(new Date(), change.id)
        // } else {
        //     await writeUpdate(new Date(), change.id, JSON.stringify(change.doc), change.seq)
        //     downloadLatestPkg(change.id, change.doc)
        // }
  
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
    
        // const topicName = 'my-topic'; // Replace with your desired topic name
        // await createTopicIfNotExists(topicName);
    
        // const messages = [
        //     { value: 'Message 1' },
        //     { value: 'Message 2' },
        //     // Add more messages as needed
        // ];
    
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
                // key: change_seq,
                value: JSON.stringify({ 'Change Seq ID': String(change_seq), 'Package Name': String(change_id) })
            }],
        });
    } finally {
        await producer.disconnect();
    }
}

// async function writeUpdate(time: Date, pkgId: string, json: string, seq: number) {
//     console.log(`updated ${pkgId} (${seq})`)

//     const d = pkgDir(pkgId)
//     await mkdir(d, { recursive: true })

//     const p = path.join(d, time.toISOString() + ".json")
//     return writeFile(p, json)
// }

// async function writeDeletion(time: Date, pkgId: string) {
//     console.log(`deleted ${pkgId}`)

//     const d = pkgDir(pkgId)
//     await mkdir(d, { recursive: true })
//     const p = path.join(d, time.toISOString() + "-DELETED.json")
//     return writeFile(p, "")
// }

// async function downloadLatestPkg(pkgId: string, doc: any) {
//     let l = doc['dist-tags'] && doc['dist-tags'].latest
//     if (!l) { console.log(`no latest version for ${doc._id}`); return }
//     let v = doc.versions && doc.versions[l]
//     if (!v) { console.log(`latest version ${l} for ${doc._id} not found`); return }
//     let tar = v.dist && v.dist.tarball
//     if (!tar) { console.log(`no tarball for version ${v} for ${doc._id}`); return }
//     let size = v.dist && v.dist.unpackedSize
//     if (!size) { console.log(`no size for ${tar} for ${doc._id}`); return }


//     let filename = path.basename(tar)
//     const d = pkgDir(pkgId)
//     await mkdir(d, { recursive: true })

//     const p = path.join(d, filename)
//     const a = access(p)

//     a.catch((r) => {
//         if (size > config.max_tar_size) { console.log(`skipping download of ${tar} for ${doc._id}, too big (${(size / 1024 / 1024).toFixed(1)}mb > max size of ${config.max_tar_size / 1024 / 1024}mb)`); return true }
//         downloadQueue.push([p, tar])
//         return true
//     }).then((v) => {
//         if (!v) console.log(`already downloaded ${tar}`)
//     })
// }

// function processDownload(input: [string, string], cb) {
//     let [p, tar] = input
//     console.log(`downloading ${tar}`)
//     let file = createWriteStream(p);
//     const request = https.get(tar, function(response) {
//         response.pipe(file);
//         file.on("finish", () => {
//             file.close();
//             console.log(`downloading ${tar} finished`);
//             cb(null, p)
//         });
//     }).on('error', (e) => { console.log(`downloading ${tar} failed ${e}`);unlink(p); cb(e, null) })
// }


// let downloadQueue: any = new Queue(processDownload, {
//     concurrent: 5, maxRetries: 1,
//     // store: {
//     //   type: 'sql',
//     //   dialect: 'sqlite',
//     //   path: config.download_queue_store
//     // }
//     }).
//     on('task_queued', () => { downloadQueueLength.set(downloadQueue.length) }).
//     on('task_finish', () => { downloadQueueLength.set(downloadQueue.length) }).
//     on('task_failed', () => { downloadQueueLength.set(downloadQueue.length) })


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