# normalize-registry-metadata
clean some common fields in package metadata objects you get from registry changes feeds


```js
var clean = require('normalize-registry-metadata')
var request = require('request')
request.get('https://skimdb.npmjs.com/registry/shelljs',function(err,res,body){
  
  var cleaned = clean(JSON.parse(body))
  // all clean. this will now work with the cli and is nearly identical to the result from registry.npmjs.org
  // nearly identical because it cleans the keys in the time object and a couple other things with dist-tags

  // no copy of the object is made. 
  // this will edit the object you pass in. 
  // you do not need to use the return value.

  var metatdata = JSON.parse(body)
  clean(metatdata)

  // this is now cleaned.
  console.log(metadata)

})

```

# API

normalize(doc [,optional options {}])

- options.tarballUrl
  - if you need to rewrite the tarball url to point to another server the values in this object are set to the corresponding key in the parsed tarball url then passed to url.format

- if the document is invalid this will return `undefined`

- runs semver.clean on all versions. 
    - `doc.version[version]`
    - `doc.version[version].version`
    - `doc.version[version]._id`
    - `doc.time[version]`
    - `doc['dist-tags'][tag] = version`

- removes dist-tags that point to uncleanable semver
- removes dist-tags that do not point to a version
- removes legacy ctime and mtime fields.
