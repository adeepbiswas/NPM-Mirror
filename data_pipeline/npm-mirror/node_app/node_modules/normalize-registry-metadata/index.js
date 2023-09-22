var semver = require('semver')
var url = require('url')

module.exports = fix

function fix(doc,options){
  options = options||{}
  if(!doc || !doc._id || doc._id.indexOf('_design/') === 0) return;

  if(doc._deleted === true || doc.error == "not_found" && doc.reason == 'deleted'){
    return;
  }

  if(!doc._attachments) doc._attachments = {}

  // couchapp removes "ctime" and "mtime" from versions
  // document contains no time object
  // example: classify
  if(doc.ctime) delete doc.ctime
  if(doc.mtime) delete doc.mtime

  if(doc.versions) {
    var map = {}
    var mismatch = false
    var origVersions = Object.keys(doc.versions)
    origVersions.forEach(function(k){
      // couchapp adds a directories to every version
      if(!doc.versions[k].directories) doc.versions[k].directories = {}

      // !!! NOTE: this could add the missing time object
      if(doc.versions[k].ctime) delete doc.versions[k].ctime
      if(doc.versions[k].mtime) delete doc.versions[k].mtime

      var version = doc.versions[k]

      // couchapp cleans all version strings on the way out
      var cleaned = semver.clean(k,true)
      if(cleaned && cleaned !== k) {

        mismatch = true
        map[k] = cleaned

        // clean the version
        doc.versions[cleaned] = version
        delete doc.versions[k]
        doc.versions[cleaned].version = cleaned

        doc.versions[cleaned]._id = doc._id+'@'+cleaned

        // clean time
        // !!! NOTE: registry couchapp does not clean the versions inside the time object.
        if(doc.time && doc.time[k]) {
          doc.time[cleaned] = doc.time[k]
          delete doc.time[k]
        }

      }

      if(options.tarballUrl){
        if(version.dist && version.dist.tarball){
          var parsed = url.parse(version.dist.tarball)
          Object.keys(options.tarballUrl).forEach(function(k){
            parsed[k] = options.tarballUrl[k]
          })
          version.dist.tarball = url.format(parsed)  
        }
      }

    })

    Object.keys(doc['dist-tags']).forEach(function(tag){
      // if i cleaned any versions. fix the dist-tags
      if(map[doc['dist-tags'][tag]]) doc['dist-tags'][tag] = map[doc['dist-tags'][tag]]
      else if(!doc.versions[doc['dist-tags'][tag]]){

        // there are a handful of documents where only the dist-tag version vlaue is malformed
        var cleaned = semver.clean(doc['dist-tags'][tag],true)
	// if dist-tag version cannot be cleaned to valid semver do not set null dist-tags
	// example: sealious-www-server has a dist-tag pointing to version "0.6"
	if(cleaned) {
          doc['dist-tags'][tag] = cleaned
          if(!doc.versions[doc['dist-tags'][tag]]){
            // version in dist tag does not exist!
            // !!! NOTE: registry-couch-app does not delete dist-tags with missing versions from output.
            delete doc['dist-tags'][tag]
          }
        } else {
          delete doc['dist-tags'][tag]
        }
      }
    })

    // !!! NOTE: registry-couch-app does not add a default latest dist-tag if it's missing.
    // related: https://github.com/npm/eng-issue-tracker/issues/63
    //if(!doc['dist-tags'].latest) {
    //}

  }

  return doc
}
