# -*- coding: utf-8 -*-

from __future__ import absolute_import

__author__ = 'nykh'

"""
scalable version of qbackup.

In real test cases where there are tens of thousands of files online, we found out it is not
practical to pull the full list of files into RAM (it can take hours).
"""

import sys
import os
import dbm

import qiniu

import qbackup.qauth
from qbackup.qbackup import MultipleBackupDriver, QiniuFlatBackup, EventLogger


class QiniuBackupScaled(QiniuFlatBackup):
    BATCH_LIMIT = 100
    TEMP_DB_FILENAME = 'temp-reomte-directory'

    def __init__(self, options, auth, logger):
        super(QiniuBackupScaled, self).__init__(options, auth, logger)

    def synch(self):
        """
        This overrides the original synch() and rebuilds an *online* version of the code
        :return:
        """
        self.logger('INFO', 'Begin synching ' + str(self.localdir)
                    + ' <=> ' + self.bucketname)
        self.validate_local_folder()
        self.logger('INFO', 'Check for download')
        remote_list = self.download_remote_files()
        self.logger('INFO', 'Check for upload')
        self.upload_local_files(remote_list)
        self.logger('INFO', 'Bucket and local folder are synched!')
        remote_list.close()
        os.remove(self.TEMP_DB_FILENAME)
        self.logger('DEBUG', 'Cleaning up completed')


    def validate_local_folder(self):
        if not self.localdir.exists():
            self.logger('WARNING', 'could not find ' + str(self.localdir)
                        + ', create folder')
            try:
                self.localdir.mkdir()
            except PermissionError:
                self.logger('ERR', 'unable to create folder. Exit now.')
                sys.exit(1)
            self.logger('INFO', 'folder created!')
        elif not self.localdir.is_dir():
            self.logger('ERR', str(self.localdir) + ' is not a directory')
            sys.exit(1)
        elif not os.access(str(self.localdir), mode=os.W_OK | os.X_OK):
            self.logger('ERR', str(self.localdir) + ' is not writable')
            sys.exit(1)

        # In addition, check for directory in a flat structure
        elif any(s.is_dir() for s in self.localdir.iterdir()):
            self.logger('ERROR', "subdirectory is detected in a "
                            "flat structure. Please review local file system "
                            "or program setting. Exit now.")
            sys.exit(1)

    def download_remote_files(self):
        """
        list all the files on the bucket (100 per batch)
        check for existence locally. Download any file that is not present
        Load the file list into a persistent database
        :return:database object
        """
        done = False
        marker = None
        bucket = qiniu.BucketManager(self.auth)

        remote_file_set = dbm.open(self.TEMP_DB_FILENAME, 'c')

        while not done:
            res, done, _ = bucket.list(self.bucketname, marker=marker,
                                       limit=self.BATCH_LIMIT)
            if not res:
                self.logger('ERROR',
                            'could not establish connection with cloud. Exit.')
                sys.exit(1)
            marker = res.get('marker')

            for remote_file in res['items']:
                key = remote_file['key']
                file = self.encoding(key)
                remote_file_set[file] = ''
                # I only need the db to serve as a set
                path = self.localdir / file
                if not path.exists():
                    self.logger('INFO', 'downloading: ' + key + ' => ' + file)
                    with open(str(path), 'wb') as filestrem:
                        self._download_file(key, filestrem, remote_file['fsize'])
        return remote_file_set

    def upload_local_files(self, remote_file_set):
        """
        os.listdir all the local files, check whether they exist remotely
        (by checking in the remote_filelist, and upload any file that doesn't.
        :param value from download_remote_files function: a list of
               remote files stored in a persistent database
        :return:None
        """
        token = self.auth.upload_token(self.bucketname)
        for file in os.listdir(str(self.localdir)):
            if file not in remote_file_set:
                self._upload_file(token,
                                  self.decoding(file),
                                  file,
                                  params={'x:a': 'a'})

