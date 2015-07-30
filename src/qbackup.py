__author__ = 'nykh'

import requests as req
import pathlib
import os
import qiniu
from qiniu import BucketManager


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
    BATCH_LIMIT = 10   # maybe optimized under real condition

    q = get_authentication()
    bucket = BucketManager(q)

    while not done:
        ret, done, info = bucket.list(bucketname, marker=marker,
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

def compare_local_and_remote(remote_key_and_ts, local_file_and_ts):
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

    for key in keylist:
        res = req.get(bucketurl + key)
        assert res.status_code == 200
        with open(str(basepath / output_policy(key)), 'wb') as of:
            of.write(res.content)
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

    q = get_authentication()
    token = q.upload_token(bucketname)
    params = {'x:a': 'a'}

    for file in filelist:
        file_path = str(basepath / file)
        mime_type = mimetypes.guess_type(file_path)
        ret, info = qiniu.put_file(token, key=file, file_path=file_path,
                                   params=params, mime_type=mime_type, check_crc=True)
        assert ret['key'] == file
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

    config = configparser.ConfigParser()
    config.read('config.ini')
    options = config['DEFAULT']

    # hardcoded now, customizable later
    bucketname = options['bucketname']
    bucketurl = options['bucketurl']
    basepath = pathlib.Path(options['basepath'])
    verbose = options.getboolean('verbose')

    if not basepath.exists():
        basepath.mkdir()
    assert basepath.exists()

    remote_key_and_timestamp = list_remote_bucket(bucketname)
    local_filename_and_mtime = list_local_files(basepath)
    down, up = compare_local_and_remote(remote_key_and_timestamp,
                                        local_filename_and_mtime)
    batch_download(bucketurl, down, basepath, verbose=verbose)
    batch_upload(bucketname, up, basepath, verbose=verbose)