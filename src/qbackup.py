__author__ = 'nykh'

import requests as req
import pathlib
import qiniu
from qiniu import BucketManager


def list_bucket(bucketname):
    """
    traverse the buckt through the Qiniu API and return a list of keys
    and timestamp
    :param bucketname:
    :return: a list of keys to download
    """
    key_list = []
    done = False
    marker = None
    BATCH_LIMIT = 10   # maybe optimized under real condition

    q = get_authentication()
    bucket = BucketManager(q)

    while not done:
        ret, done, info = bucket.list(bucketname, marker=marker,
                                      limit=BATCH_LIMIT)
        marker = ret.get('marker')
        for item in ret['items']:
            key_list.append((item['key'], item['putTime']))

    return key_list


def compare_local_and_remote(remote_key_and_ts, basepath):
    '''
    Compare the local files and remote list of items,
    produce a tuple of two lists, one lists files on remote
    not in local drive (to be downloaded), the other lists files
    that exist on the local drive but not on remote (to be uploaded).
    :param remote_key_and_ts:
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

    downloadend = []
    uploadend = []
    for key, ts in remote_key_and_ts:
        localpath = basepath / key
        if not localpath.exists():
            downloadend.append(key)
        else:
            cmp = compare_timestamp(ts, localpath.stat().st_mtime)
            if cmp > 0:  # remote is later than local
                downloadend.append(key)

    return (downloadend, uploadend)


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

    key_and_timestamp = list_bucket(bucketname)
    down, up = compare_local_and_remote(key_and_timestamp, basepath)
    batch_download(bucketurl, down, basepath, verbose=verbose)
    batch_upload(bucketname, up, basepath, verbose=True)