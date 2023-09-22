
var test = require('tape')
var normalize = require('../')
var badVersions = require('./fixtures/skim-shelljs.json')
var deletedJson = require('./fixtures/skim-deleted.json')
var spaceTag = require('./fixtures/skim-twilio.json')
var mtimeJson = require('./fixtures/skim-classify.json')


test("can fix versions",function(t){
  var badCopy = JSON.parse(JSON.stringify(badVersions))
  var cleaned = normalize(badVersions)

  t.ok(cleaned,'should have cleaned')

  t.ok(badCopy.versions['0.0.5pre1'],'should have malformed version')
  t.ok(!cleaned.versions['0.0.5pre1'],'should have removed malformed version')
  t.ok(cleaned.versions['0.0.5-pre1'],'should have cleaned version')
  t.ok(cleaned.time['0.0.5-pre1'],'should have fixed time object also')

  t.end()

})

test("cleans dist-tags pointing to  missing versions",function(t){
  var tagCopy = JSON.parse(JSON.stringify(spaceTag))

  normalize(tagCopy)

  t.ok(Object.keys(spaceTag['dist-tags']).indexOf('beta') > -1,'unclean should have beta tag')
  t.equals(Object.keys(tagCopy['dist-tags']).indexOf('beta'),-1,'clean should not have beta tag')

  t.end()
})

test("cleans ctime and mtime",function(t){
  t.ok(mtimeJson.ctime,'should have ctime value')
  t.ok(mtimeJson.mtime,'should have mtime value')

  var versions = Object.keys(mtimeJson.versions)
  t.ok(mtimeJson.versions[versions[0]].ctime,'the first version should have ctime before cleaning')
  normalize(mtimeJson)
  t.ok(!mtimeJson.ctime,'should not have ctime value')
  t.ok(!mtimeJson.mtime,'should not have mtime value')
  t.ok(!mtimeJson.versions[versions[0]].ctime,'the first version should not have ctime after cleaning')
  t.end()  
})


test("deleted docs return undefined",function(t){
  t.equals(normalize(deletedJson),undefined,"deleted json should be undefined")
  t.end()
})

test("design docs return undefined",function(t){
  t.equals(normalize({_id:"_design/foo"}),undefined,'design doc return undefined')
  t.end()
})

test("objects without _id return undefined",function(t){
  delete badVersions._id
  t.equals(normalize(badVersions),undefined,'is missing _id should return undefined')
  t.end()
})

test("undefined goes in undefined comes out",function(t){
  t.equals(normalize(),undefined,'should be undefined')
  t.end()
})

test("tarballUrl options",function(t){
  normalize(spaceTag,{tarballUrl:{protocol:'https:'}})

  t.equals(spaceTag.versions['1.4.0'].dist.tarball,'https://registry.npmjs.org/twilio/-/twilio-1.4.0.tgz','protocol should be rewritten')  

  t.end()
})

