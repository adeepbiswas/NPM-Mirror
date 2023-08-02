import os
import requests
import json
import tarfile
import zipfile
import re

LOCAL_PACKAGE_DIR = "packages"

def remove_special_characters(input_string):
    # Define a regex pattern to match all non-alphanumeric characters except "/"
    pattern = r"[^a-zA-Z0-9/]"
    
    # Use re.sub() to replace all matched characters with an empty string
    cleaned_string = re.sub(pattern, "", input_string)
    # print("cleam string - ", cleaned_string)
    return cleaned_string

def create_directory_structure(package_name):
    # Create parent directory for all packages if it doesn't exist
    if not os.path.exists(LOCAL_PACKAGE_DIR):
        os.mkdir(LOCAL_PACKAGE_DIR)

    # Create subdirectories for each alphabet (A-Z)
    first_char = package_name[0].upper()
    # if not first_char.isalpha():
    #     first_char = "NonAlphabetic"
    alpha_dir = os.path.join(LOCAL_PACKAGE_DIR, first_char)
    if not os.path.exists(alpha_dir):
        os.mkdir(alpha_dir)

    # Create subdirectory for each package in the corresponding alphabet directory
    if '/' in package_name:
        package_dir = alpha_dir
        segments = package_name.split("/")
        for segment in segments:
            package_dir = os.path.join(package_dir, segment)
            if not os.path.exists(package_dir):
                os.mkdir(package_dir)
    else:
        package_dir = os.path.join(alpha_dir, package_name)
        print("Package Name", package_name)
        if not os.path.exists(package_dir):
            os.mkdir(package_dir)

    return package_dir

def download_document_and_package(change):
    doc = change.get('doc') #storing only doc part currently
    if doc:
        # package_name = doc.get('_id')
        package_name = change.get('id')
        if package_name:
            # package_name = remove_special_characters(package_name)
            package_dir = create_directory_structure(package_name)

            # Save the document as a JSON file
            if "/" in package_name:
                segments = package_name.split("/")
                name = segments[-1]
            else:
                name = package_name
            doc_filename = f"{name}_doc.json"
            doc_path = os.path.join(package_dir, doc_filename)
            with open(doc_path, 'w') as doc_file:
                json.dump(doc, doc_file)

            # Save the updated package as a tar file
            # print("----------")
            # print(package_name)
            # print(doc.keys())
            latest = doc['dist-tags']['latest']
            package_url = doc['versions'][latest]['dist']['tarball']
            # print("----------")
            # package_url = f"https://registry.npmjs.org/{package_name}/-/{package_name}-{doc['dist-tags']['latest']}.tgz"
            package_filename = f"{name}_package.tgz"
            package_path = os.path.join(package_dir, package_filename)
            response = requests.get(package_url)
            print("Response - ",response)
            if response.status_code == 200:
                with open(package_path, 'wb') as package_file:
                    package_file.write(response.content)
                print("saved")
            return doc_path, package_path
    return None, None

def compress_files(package_name, revision_id, doc_path, package_path):
    compressed_filename = f"{package_name}_{revision_id}.zip"
    with zipfile.ZipFile(compressed_filename, 'w') as zip_file:
        if doc_path:
            zip_file.write(doc_path, os.path.basename(doc_path))
            os.remove(doc_path)  # Remove the individual JSON file after compression
        if package_path:
            zip_file.write(package_path, os.path.basename(package_path))
            os.remove(package_path)  # Remove the individual tar file after compression

def store_change_details(change, compressed_filename, change_count):
    # Store the important details regarding the change in the local CouchDB database.
    # Replace the following with your code to interact with the local CouchDB.

    change_id = change['id']
    timestamp = change['timestamp']
    package_name = change['doc']['name']
    change_type = change.get('type')
    # Add any other relevant details you want to store in the database.

def stream_npm_updates():
    url = 'https://replicate.npmjs.com/_changes?include_docs=true&feed=continuous&heartbeat=10000&style=all_docs&conflicts=true&since=25318023' #&limit=20'

    response = requests.get(url, stream=True)

    if response.status_code != 200:
        print(f'Error connecting to the CouchDB stream: {response.status_code}')
        return

    # print(response)
    i = 0

    for line in response.iter_lines():
        i += 1
        # print(i)
        # print(line)
        if line:
            change = json.loads(line)
            print(change['seq'])
            print(change['id'])
            print(change['changes'])
            print(change['doc']['_rev'])
            print(change.keys())
            doc_path, package_path = download_document_and_package(change)
            print(doc_path)
            if doc_path or package_path:
                package_name = change['id']
                if "/" in package_name:
                    segments = package_name.split("/")
                    name = segments[-1]
                else:
                    name = package_name
                compress_files(name, change['doc']['_rev'], doc_path, package_path)
                # Get the package name to store the change details
                package_name = change.get('doc', {}).get('name')
                if package_name:
                    # Update the change count for the package and get the updated count
                    # change_count = update_change_count(package_name)
                    # Store important details regarding the change in the local CouchDB
                    # store_change_details(change, f"{change['id']}_{change['timestamp']}.zip", change_count)

stream_npm_updates()
