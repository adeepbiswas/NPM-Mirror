import requests
import json

def stream_npm_updates():
    url = 'https://replicate.npmjs.com/_changes?include_docs=true&feed=continuous&heartbeat=10000&style=all_docs&conflicts=true' # &descending=true' #&since=now&style=all_docs'

    response = requests.get(url, stream=True)

    if response.status_code != 200:
        print(f'Error connecting to the CouchDB stream: {response.status_code}')
        return

    print(response)
    
    for line in response.iter_lines():
        if line:
            change = json.loads(line)
            doc = change.get('doc')
            if doc:
                # Process the document here
                print(doc)
                
                # change_type = change.get('type')
                # if change_type in ['created', 'updated', 'deleted']:
                #     # Process the document here
                #     print(f"Change Type: {change_type}")
                #     print(doc)

stream_npm_updates()
