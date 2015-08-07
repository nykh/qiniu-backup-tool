# -*- coding: utf-8 -*-

__author__ = 'nykh'

"""
An example of validating script that confirms the correct execution of __main__.py.
To use the script, set the `purge` option in the config file to False, so that the
temporary database will not be purged at the end of execution. The script uses the
database to validate the content of the folder.

The criteria for downloading consistency is
- each file in the database is in the local folder
- each file in the local folder has a size no less than that recorded in the database

The criteria for uploading consistency is
- each file in the local folder is in the database
We assume each upload is successful for now
"""

import dbm
import os
from pathlib import Path

BUCKET = 'llce'
DBM_FILE = 'tmp/llce-2015-08-07-16-17-07'
LOCALDIR = '../../llce'

path = Path(LOCALDIR)
db = dbm.open(DBM_FILE, 'r')

encode = lambda s: s.replace('/', '%2F')
decode = lambda s: s.replace('%2F', '/')

def evaluate_download():
    flag = True
    for key in db.keys():
        key = key.decode()
        file = path / encode(key)
        if not file.exists():
            print('key ' + key + ' is missing from local directory')
            flag = False
        elif file.stat().st_size < int(db[key]):
            print('key ' + key + ' has failed to download')
            flag = False
    return flag

def evaluate_upload():
    flag = True
    for file in path.iterdir():
        file = file.relative_to(path).as_posix()
        if file not in db:
            print('file ' + str(file) + ' is missing from remote directory')
            flag = False
    return flag


print('Validating bucket ' + BUCKET)
print('using database ' + DBM_FILE + ' and ' + LOCALDIR)
if evaluate_download() and evaluate_upload():
    print('All correct!')

db.close()
