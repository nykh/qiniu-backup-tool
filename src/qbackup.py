__author__ = 'nykh'

import requests as req


def batch_download(bucketurl, keylist, output_policy):
    '''
    simple function that batch download list of resources from qiniu bucket
    :except: raises exception if any of the request return an error
    :param bucketurl: base URL for the bucket
    :param keylist: list of keys for downloading
    :param output_policy: callback function that determines the output
                          filename based on the key
    :return:
    '''
    for key in keylist:
        res = req.get(bucketurl + key)
        if res.status_code != 200:
            raise Exception
        with open(output_policy(key), 'wb') as of:
            of.write(res.content)


if __name__ == '__main__':
    # hardcoded now, customizable later
    bucketname = 'llcetest'
    bucketurl = 'http://7xkpk9.com1.z0.glb.clouddn.com/'

    batch_download(bucketurl,
                   ['test1.txt', 'test2.txt', 'russia.jpg'],
                   lambda x: x)
