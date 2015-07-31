__author__ = 'nykh'

import qiniu


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
