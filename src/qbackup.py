__author__ = 'nykh'

import pathlib
import os
import time
import qiniu
from qiniu import BucketManager

BATCH_LIMIT = 10   # maybe optimized under real condition


def list_remote_bucket(bucketname):
    """
    traverse the buckt through the Qiniu API and return a list of keys
    and timestamp
    :param bucketname:
    :return: a dict mapping key to upload time
    """
    key_list = {}
    done = False
    marker = None

    auth = get_authentication()
    bucket = BucketManager(auth)

    while not done:
        ret, done, _ = bucket.list(bucketname, marker=marker,
                                   limit=BATCH_LIMIT)
        marker = ret.get('marker')
        for resource in ret['items']:
            key_list[resource['key']] = resource['putTime']

    return key_list


def list_local_files(basepath):
    '''

    :param basepath:
    :return:a dict mapping filename to last modified time (ST_MTIME)
    '''
    local_filename_and_mtime = {}
    for path, _, files in os.walk(str(basepath)):
        for file in files:
            fullpath = os.path.join(path, file)
            keypath = fullpath[len(str(basepath))+1:]
            # strip the basepath from fullpath, such that filename == key
            mtime = os.stat(fullpath).st_mtime
            local_filename_and_mtime[keypath] = mtime
    return local_filename_and_mtime


def compare_local_and_remote(remote_key_and_ts, local_filename_and_mtime):
    '''
    Compare the local files and remote list of items,
    produce a tuple of two lists, one lists files on remote
    not in local drive (to be downloaded), the other lists files
    that exist on the local drive but not on remote (to be uploaded).
    :param remote_key_and_ts: output of the `list_bucket` function
    :param basepath:
    :rtype: object
    :return: ([files to be downloaded], [files to be uploaded])
    '''

    def compare_timestamp(remote, local):
        '''
        on Qiniu cloud, file timestamp are with unit of 100 ns (epoch),
        locally however the timestamp is in sec (epoch) and float number.
        Considering the program is expected to run weekly, the comparison
        may well be done in the unit of second. I consider collision to be
        highly unlikely.

        Problem: it seems in fact Qiniu timestamp is in the unit of 1us,
        not 100ns. I take liberty and use 10e6 instead of 10e7 as the ratio.
        '''
        remote /= int(10e6)
        local = int(local)
        if remote > local:
            return 1
        elif remote < local:
            return -1
        else:
            return 0

    download = []
    upload = []

    remote_files = set(remote_key_and_ts)
    local_files = set(local_filename_and_mtime)

    both = local_files.intersection(remote_files)

    download.extend(remote_files.difference(local_files))
    upload.extend(local_files.difference(remote_files))
    for key in both:
        cmp = compare_timestamp(remote_key_and_ts[key],
                                local_filename_and_mtime[key])
        if cmp > 0:  # remote is later than local
            download.append(key)

    return (download, upload)


def batch_download(bucketurl, keylist, basepath, output_policy=lambda x: x,
                   verbose=False):
    '''
    side-effect: batch download list of resources from qiniu bucket
    :except: raises exception if any of the request return an error
    :param bucketurl: base URL for the bucket
    :param keylist: list of keys for downloading
    :param output_policy: callback function that determines the output
                          filename based on the key
    :param verbose: if True print each file downloaded
    '''
    import requests as req

    for key in keylist:
        res = req.get(bucketurl + key)
        assert res.status_code == 200
        process_key = output_policy(key)
        if '/' in process_key:
            # recursively validate each level
            levels = os.path.dirname(process_key).split('/')
            dirpath = basepath
            for level in levels:
                dirpath /= level
                if not dirpath.exists():
                    os.mkdir(str(dirpath))
        with open(str(basepath / process_key), 'wb') as local_copy:
            local_copy.write(res.content)
        if verbose:
            print('downloaded: ' + key)


def batch_upload(bucketname, filelist, basepath, verbose=False):
    '''

    :param bucketname:
    :param filelist: list of file names (including path) to be uploaded
    :param basepath:
    :param verbose: if True print each file uploaded
    :return:
    '''
    import mimetypes

    auth = get_authentication()
    token = auth.upload_token(bucketname)
    params = {'x:a': 'a'}

    for file in filelist:
        file_path = str(basepath / file)
        mime_type = mimetypes.guess_type(file_path)[0]
        # guess_type() return a tuple (mime_type, encoding), only mime_type is needed
        ret, _ = qiniu.put_file(token, key=file,
                                file_path=file_path, params=params,
                                mime_type=mime_type, check_crc=True)
        assert ret['key'] == file

        future = time.time() + 10  # sec since Epoch
        os.utime(file_path, times=(future, future))
        # reset the atime and mtime in the future so that the file doesn't
        # trigger the download criteria (remote timestamp > local timestamp)

        if verbose:
            print('uploaded: ' + file)


def get_authentication():
    '''
    precondition: file "keys" contains the following content
    "access_key: ___
     secret_key: ___"
    extracts the authenticate keys and return an Auth object
    :rtype : object
    :return: qiniu.Auth object
    '''
    with open('keys', 'r') as keyfile:
        access_key = keyfile.readline()[12:].strip()
        secret_key = keyfile.readline()[12:].strip()
    return qiniu.Auth(access_key, secret_key)


if __name__ == '__main__':
    import configparser

    CONFIG = configparser.ConfigParser()
    CONFIG.read('config.ini')
    OPTIONS = CONFIG['DEFAULT']

    # hardcoded now, customizable later
    BUCKET_NAME = OPTIONS['bucketname']
    BUCKET_URL = OPTIONS['bucketurl']
    BASE_PATH = pathlib.Path(OPTIONS['basepath'])
    VERBOSE = OPTIONS.getboolean('verbose')

    if not BASE_PATH.exists():
        BASE_PATH.mkdir()
    assert BASE_PATH.exists()

    REMOTE_KEY_AND_TIMESTAMP = list_remote_bucket(BUCKET_NAME)
    LOCAL_FILE_AND_MTIME = list_local_files(BASE_PATH)
    DOWNLOAD_FILE_LIST, UPLOAD_FILE_LIST = compare_local_and_remote(
        REMOTE_KEY_AND_TIMESTAMP, LOCAL_FILE_AND_MTIME)
    batch_download(BUCKET_URL, DOWNLOAD_FILE_LIST, BASE_PATH, verbose=VERBOSE)
    batch_upload(BUCKET_NAME, UPLOAD_FILE_LIST, BASE_PATH, verbose=VERBOSE)
