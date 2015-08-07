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
from pathlib import Path
import dbm

from arrow import now
import qiniu

from qbackup.qbackup import QiniuFlatBackup


class QiniuBackupScaled(QiniuFlatBackup):
    BATCH_LIMIT = 100
    TEMP_DB_DIR = Path('tmp')
    TEMP_DB = 'temp-reomte-directory'
    MAX_ATTEMPT = 4

    def __init__(self, options, auth, logger):
        super(QiniuBackupScaled, self).__init__(options, auth, logger)
        self.purge = options.getboolean('purge', fallback=True)

    def synch(self):
        """
        This overrides the original synch() and rebuilds an *online* version of the code
        :return:
        """
        self.logger('INFO', 'Begin synching ' + str(self.localdir)
                    + ' <=> ' + self.bucketname)
        self.validate_local_folder()

        if not self.TEMP_DB_DIR.exists():
            self.logger('DEBUG', 'Create temporary folder')
            self.TEMP_DB_DIR.mkdir()
        temp_db = self.bucketname + '-' + now().format('YYYY-MM-DD-HH-mm-ss')
        self.logger('DEBUG', 'Create database file tmp/' + temp_db)

        with dbm.open(str(self.TEMP_DB_DIR / temp_db), 'c') as remote_file_db:
            self.logger('INFO', 'Check for download')
            self.download_remote_files(remote_file_db)
            self.logger('INFO', 'Check for upload')
            self.upload_local_files(remote_file_db)
            self.logger('INFO', 'Bucket and local folder are synched!')

        if self.purge:
            self.logger('DEBUG', 'removing temporary database files...')
            for file in self.TEMP_DB_DIR.iterdir():
                file.unlink()  # remove file
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

    def download_remote_files(self, remote_file_set):
        """
        list all the files on the bucket (100 per batch)
        check for existence locally. Download any file that is not present
        Load the file list into a persistent database
        :return:database object
        """
        done = False
        marker = None
        bucket = qiniu.BucketManager(self.auth)

        while not done:
            res, done, _ = bucket.list(self.bucketname, marker=marker,
                                       limit=self.BATCH_LIMIT)
            if not res:
                self.logger('ERROR',
                            'could not establish connection with cloud. Exit.')
                raise ConnectionError('could not establish connection with cloud')
            marker = res.get('marker')

            for remote_file in res['items']:
                key = remote_file['key']
                file = self.encoding(key)
                remote_file_set[file] = str(remote_file['fsize'])
                # I only need the db to serve as a set
                path = self.localdir / file
                if not path.exists():
                    attempt = 0
                    while True:
                        if attempt > self.MAX_ATTEMPT:
                            self.logger('ERROR', 'The file has failed to download. '
                                                 'Removing incomplete file')
                            if path.exists():
                                path.unlink()
                            break

                        try:
                            attempt += 1
                            with open(str(path), 'wb') as filestrem:
                                self._download_file(key, filestrem, remote_file['fsize'])
                        except ConnectionError:
                            self.logger('WARN',
                                        'There is trouble downloading the file. '
                                        'Attempt ' + str(attempt) + ' out of '
                                        + str(self.MAX_ATTEMPT))
                            continue

                        # no exception is thrown
                        if path.stat().st_size == remote_file['fsize']:
                            self.logger('INFO', 'file has been downloaded successfully.')
                            break  # success!
                        else:
                            self.logger('WARN',
                                        'file downloaded is not complete.'
                                        'Attempt ' + str(attempt) + ' out of '
                                        + str(self.MAX_ATTEMPT))
        return remote_file_set

    def upload_local_files(self, remote_file_set):
        """
        os.listdir all the local files, check whether they exist remotely
        (by checking in the remote_filelist, and upload any file that doesn't.
        :param remote_file_set: a mapping of keys to file size stored in database
        :return:None
        """
        token = self.auth.upload_token(self.bucketname)
        for file in os.listdir(str(self.localdir)):
            if file not in remote_file_set:
                key = self.decoding(file)
                self._upload_file(token,
                                  key,
                                  file,
                                  params={'x:a': 'a'})
                # ideally, remote_file_set[key] should store the
                # file size of the uploaded file,
                # currently I only put in a zero for every newly uploaded file
                # and assume uploading is handled correctly
                remote_file_set[key] = '0'
