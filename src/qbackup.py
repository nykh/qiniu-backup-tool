__author__ = 'nykh'

import pathlib
import os
import sys
import datetime
import time
import qiniu
from qiniu import BucketManager
import qauth


class QiniuBackup:
    BATCH_LIMIT = 10   # maybe optimized under real condition

    def __init__(self, options, auth):
        self.bucketname = options['bucketname']
        self.bucketurl = options['bucketurl']
        self.basepath = pathlib.Path(options['basepath'])

        self.verbose = options.getboolean('verbose', fallback=False)
        self.log_to_file = options.getboolean('log', fallback=False)

        self.ev = EventLogger(verbose=self.verbose,
                                  log_to_file=self.log_to_file)

        self.auth = auth

    def synch(self):
        '''
        the main synchroization logic happens here
        :return:None
        '''
        self.ev.log('INFO', 'Begin synching ' + str(self.basepath)
                  + ' <=> Bucket ' + self.bucketname)

        self.validate_local_folder()

        download_file_list, upload_file_list = \
            QiniuBackup.compare_local_and_remote(self.list_remote_bucket(),
                                                 self.list_local_files())
        self.batch_download(download_file_list)
        self.batch_upload(upload_file_list)

        # print a message if no file is transfered
        if not download_file_list and not upload_file_list:
            self.ev.log('INFO', "Cloud and local folder are already synched!")

    def validate_local_folder(self):
        if not self.basepath.exists():
            self.ev.log('WARNING', 'could not find ' + str(self.basepath)
                      + ', create folder')
            try:
                self.basepath.mkdir()
            except PermissionError:
                self.ev.log('ERR', 'unable to create folder. Exit now.')
                sys.exit(1)
            self.ev.log('INFO', 'folder created!')
        elif not self.basepath.is_dir():
            self.ev.log('ERR', str(self.basepath) + ' is not a directory')
            sys.exit(1)
        elif not os.access(str(self.basepath), mode=os.W_OK | os.X_OK):
            self.ev.log('ERR', str(self.basepath) + ' is not writable')
            sys.exit(1)


    def list_remote_bucket(self):
        """
        traverse the buckt through the Qiniu API and return a list of keys
        and timestamp
        :param bucketname:
        :return: a dict mapping key to upload time
        """
        key_list = {}
        done = False
        marker = None

        bucket = BucketManager(self.auth)

        while not done:
            ret, done, _ = bucket.list(self.bucketname, marker=marker,
                                       limit=self.BATCH_LIMIT)
            marker = ret.get('marker')
            for resource in ret['items']:
                key_list[resource['key']] = resource['putTime']

        return key_list

    def list_local_files(self):
        '''

        :param basepath:
        :return:a dict mapping filename to last modified time (ST_MTIME)
        '''
        local_filename_and_mtime = {}
        for path, _, files in os.walk(str(self.basepath)):
            for file in files:
                fullpath = os.path.join(path, file)
                keypath = fullpath[len(str(self.basepath))+1:]
                # strip the basepath from fullpath, such that filename == key
                mtime = os.stat(fullpath).st_mtime
                local_filename_and_mtime[keypath] = mtime
        return local_filename_and_mtime

    @staticmethod
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
        download = []
        upload = []

        remote_files = set(remote_key_and_ts)
        local_files = set(local_filename_and_mtime)

        both = local_files.intersection(remote_files)

        download.extend(remote_files.difference(both))
        upload.extend(local_files.difference(both))
        for key in both:
            cmp = QiniuBackup.compare_timestamp(remote_key_and_ts[key],
                                                local_filename_and_mtime[key])
            if cmp > 0:  # remote is later than local
                download.append(key)

        return (download, upload)

    @staticmethod
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

    def batch_download(self, keylist, output_policy=lambda x: x):
        '''
        side-effect: batch download list of resources from qiniu bucket
        :except: raises exception if any of the request return an error
        :param keylist: list of keys for downloading
        :param output_policy: callback function that determines the output
                              filename based on the key
        :return None
        '''
        if not keylist:
            return

        import requests as req

        for key in keylist:
            res = req.get(self.bucketurl + key)
            assert res.status_code == 200
            process_key = output_policy(key)
            if '/' in process_key:
                # recursively validate each level
                levels = os.path.dirname(process_key).split('/')
                dirpath = self.basepath
                for level in levels:
                    dirpath /= level
                    if not dirpath.exists():
                        os.mkdir(str(dirpath))
            with open(str(self.basepath / process_key), 'wb') as local_copy:
                local_copy.write(res.content)
            if self.verbose:
                self.ev.log('INFO', 'downloaded: ' + key)

    def batch_upload(self, filelist):
        '''
        same as batch_download but for uploadging, requires authentication
        :param filelist: list of file names (including path) to be uploaded
        :return:None
        '''
        if not filelist:
            return

        import mimetypes

        token = self.auth.upload_token(self.bucketname)
        params = {'x:a': 'a'}

        for file in filelist:
            file_path = str(self.basepath / file)
            mime_type = mimetypes.guess_type(file_path)[0]
            # guess_type() return a tuple (mime_type, encoding),
            # only mime_type is needed
            ret, _ = qiniu.put_file(token, key=file,
                                    file_path=file_path, params=params,
                                    mime_type=mime_type, check_crc=True)
            assert ret['key'] == file

            future = time.time() + 10  # sec since Epoch
            os.utime(file_path, times=(future, future))
            # reset the atime and mtime in the future so that the file doesn't
            # trigger the download criteria (remote ts > local ts)

            if self.verbose:
                self.ev.log('INFO', 'uploaded: ' + file)


class EventLogger:
    def __init__(self, verbose=False, log_to_file=False):
        if log_to_file:
            self.logfile = open('qbackup-{}.log'.format(
                datetime.datetime.now().strftime('%y-%m-%d_%H-%M-%S')
            ), 'w')

            if verbose:
                def _log(tag, msg):
                    msg = EventLogger.format(tag, msg)
                    self.logfile.write(msg + '\n')
                    print(msg)
                self.log = _log
            else:
                def _log(tag, msg):
                    self.logfile.write(EventLogger.format(tag, msg) + '\n')
                self.log = _log
        elif verbose:
            def _log(tag, msg):
                print(EventLogger.format(tag, msg))

            self.log = _log

    def __del__(self):
        if self.logfile:
            self.logfile.close()

    @staticmethod
    def format(tag, msg):
        return "{0} [{1}] {2}".format(datetime.datetime.now(),
                                      tag, msg)


if __name__ == '__main__':
    import configparser

    CONFIG = configparser.ConfigParser()
    if not CONFIG.read('config.ini'):
        print(EventLogger.format('ERR', 'could not read config file!'))
        sys.exit(1)

    options = CONFIG['DEFAULT']

    auth = qauth.get_authentication()
    qbackup = QiniuBackup(options, auth)
    qbackup.synch()
