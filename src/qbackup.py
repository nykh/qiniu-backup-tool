__author__ = 'nykh'

import requests as req
import qiniu
from qiniu import BucketManager


def list_bucket(bucketname):
    """
    traverse the buckt through the Qiniu API and return a list of keys
    :param bucketname:
    :return: a list of keys to download
    """
    key_list = []
    done = False
    marker = None

    access_key, secret_key = get_authentication()
    q = qiniu.Auth(access_key, secret_key)
    bucket = BucketManager(q)

    while not done:
        ret, done, info = bucket.list(bucketname, marker=marker, limit=10)
        marker = ret.get('marker')
        for item in ret['items']:
            key_list.append(item['key'])

    return key_list


def batch_download(bucketurl, keylist, output_policy=lambda x: x):
    '''
    side-effect: batch download list of resources from qiniu bucket
    :except: raises exception if any of the request return an error
    :param bucketurl: base URL for the bucket
    :param keylist: list of keys for downloading
    :param output_policy: callback function that determines the output
                          filename based on the key
    '''

    for key in keylist:
        res = req.get(bucketurl + key)
        if res.status_code != 200:
            raise Exception
        with open(output_policy(key), 'wb') as of:
            of.write(res.content)


def get_authentication():
    '''

    :rtype : object
    :return: tuple of (access_key, secret_key)
    '''
    with open('keys', 'r') as keyfile:
        access_key = keyfile.readline()[12:].strip()
        secret_key = keyfile.readline()[12:].strip()
    return (access_key, secret_key)


if __name__ == '__main__':
    # hardcoded now, customizable later
    bucketname = 'llcetest'
    bucketurl = 'http://7xkpk9.com1.z0.glb.clouddn.com/'

    key_list = list_bucket(bucketname)

    batch_download(bucketurl, key_list)
