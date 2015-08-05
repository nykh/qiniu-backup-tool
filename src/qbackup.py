__author__ = 'nykh'

import pathlib
import os
import sys
import mimetypes
import datetime
import time
import qiniu
from qiniu import BucketManager
import progressbar
import src.qauth as qauth
import requests as req


class QiniuBackup:
    BATCH_LIMIT = 10  # maybe optimized under real condition
    CHUNK_SIZE = 1024 * 1024

    def __init__(self, options, auth, logger=None):
        self.bucketname = options['bucketname']
        self.bucketurl = options['bucketurl']
        self.localdir = pathlib.Path(options['local_dir'])

        self.verbose = options.getboolean('verbose', fallback=False)
        self.log_to_file = options.getboolean('log', fallback=False)

        self.download_size_threshold = options.getint('size_threshold',
                                                      fallback=1024) * 1024
        if self.download_size_threshold < self.CHUNK_SIZE * 2:
            self.download_size_threshold = self.CHUNK_SIZE * 2

        if logger is None:
            self.logger = EventLogger(verbose=self.verbose,
                                      log_to_file=self.log_to_file)
        else:
            self.logger = logger

        self.auth = auth

    def synch(self):
        """
        the main synchroization logic happens here
        :return:None
        """
        self.logger('INFO', 'Begin synching ' + str(self.localdir)
                    + ' <=> Bucket ' + self.bucketname)

        self.validate_local_folder()

        local_timestamp = self._list_local_files()
        remote_timstamp, big = self._list_remote_bucket()

        download_file_list, upload_file_list = \
            QiniuBackup._compare_local_and_remote(remote_timstamp,
                                                  local_timestamp)
        self._batch_download(download_file_list, big)
        self._batch_upload(upload_file_list)

        self.logger('INFO', "Bucket and local folder are synched!")

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

    def _list_remote_bucket(self):
        """
        traverse the buckt through the Qiniu API and return a list of keys
        and timestamp
        :except no connection is established
        :return: a dict mapping key to upload time
        """
        key_list = {}
        big_file = {}
        done = False
        marker = None

        bucket = BucketManager(self.auth)

        while not done:
            res, done, _ = bucket.list(self.bucketname, marker=marker,
                                       limit=self.BATCH_LIMIT)
            if not res:
                self.logger('ERROR',
                            'could not establish connection with cloud. Exit.')
                sys.exit(1)
            marker = res.get('marker')
            for resource in res['items']:
                key_list[resource['key']] = resource['putTime']
                big_file[resource['key']] = resource['fsize'] \
                    if resource['fsize'] > self.download_size_threshold * 2 \
                    else 0
        return key_list, big_file

    def _list_local_files(self):
        """
        :return:a dict mapping filename to last modified time (ST_MTIME)
        """
        local_filename_and_mtime = {}
        for path, _, files in os.walk(str(self.localdir)):
            for file in files:
                fullpath = pathlib.Path(path, file)
                keypath = self.__decode_spec_characters(
                    fullpath.relative_to(self.localdir))
                # strip the basepath from fullpath, such that filename == key
                # drop any @/
                mtime = fullpath.stat().st_mtime
                local_filename_and_mtime[keypath] = mtime
        return local_filename_and_mtime

    @staticmethod
    def __encode_spec_character(key):
        """
        translate key to local file path
        ^/ -> ^@/
        @ -> @@
        // -> /@/
        :param key string
        :return local file path
        """
        key = key.replace('@', '@@') \
            .replace('//', '/@/') \
            .replace('//', '/@/')
        if key.startswith('/'):
            key = '@' + key
        return key

    @staticmethod
    def __decode_spec_characters(local_path):
        """
        translate local file path to key string
        to posix
        ^@/ -> ^/
        @@ -> @
        /@/ -> //
        :param local_path
        :return: key string
        """
        pathname = local_path.as_posix()
        return pathname.replace('@/', '/').replace('@@', '@')

    @staticmethod
    def _compare_local_and_remote(remote_key_and_ts, local_filename_and_mtime):
        """
        Compare the local files and remote list of items,
        produce a tuple of two lists, one lists files on remote
        not in local drive (to be downloaded), the other lists files
        that exist on the local drive but not on remote (to be uploaded).
        :param local_filename_and_mtime: output of `list_remote_files` function
        :param remote_key_and_ts: output of the `list_local_flles` function
        :rtype: object
        :return: ([files to be downloaded], [files to be uploaded])
        """
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

        return download, upload

    @staticmethod
    def compare_timestamp(remote, local):
        """
        on Qiniu cloud, file timestamp are with unit of 100 ns (epoch),
        locally however the timestamp is in sec (epoch) and float number.
        Considering the program is expected to run weekly, the comparison
        may well be done in the unit of second. I consider collision to be
        highly unlikely.

        Problem: it seems in fact Qiniu timestamp is in the unit of 1us,
        not 100ns. I take liberty and use 10e6 instead of 10e7 as the ratio.
        """
        remote /= int(10e6)
        local = int(local)
        if remote > local:
            return 1
        elif remote < local:
            return -1
        else:
            return 0

    def _batch_download(self, keylist, big_file_list=None):
        """
        side-effect: batch download list of resources from qiniu bucket
        :except: raises exception if any of the request return an error
        :param keylist: list of keys for downloading
        :return None
        """
        if not keylist:
            return

        for key in keylist:
            self.logger('INFO', 'downloading: ' + key)
            file = QiniuBackup.__encode_spec_character(key)
            subpath = self.localdir / file
            parents = [str(p) for p in subpath.parents]
            parents.sort(key=len)
            for parent in parents[1:]:  # ignore ','
                dirpath = self.localdir / parent
                if not dirpath.exists():
                    dirpath.mkdir()
            with open(str(self.localdir / subpath), 'wb') as local_copy:
                self._download_file(key, local_copy, big_file_list)

    def _batch_upload(self, filelist):
        """
        same as batch_download but for uploadging, requires authentication
        :param filelist: list of file names (including path) to be uploaded
        :return:None
        """
        if not filelist:
            return

        token = self.auth.upload_token(self.bucketname)
        params = {'x:a': 'a'}

        for key in filelist:
            filename = QiniuBackup.__encode_spec_character(key)
            self._upload_file(token, key, filename, params)

    def _download_file(self, key, file, big_file_list):
        if big_file_list and big_file_list[key]:
            res = req.get(self.bucketurl + key, stream=True)
            if res.status_code != 200:
                self.logger('WARN',
                            'downloading ' + key + ' failed.')
                return

            progress_bar = ProgressHandler(self.verbose)
            progress = 0
            total = big_file_list[key]
            for chunk in res.iter_content(chunk_size=self.CHUNK_SIZE):
                if not chunk:
                    continue
                file.write(chunk)
                file.flush()
                os.fsync(file)

                progress += self.CHUNK_SIZE
                if progress > total:
                    progress_bar(total, total)
                else:
                    progress_bar(progress, total)

        else:
            res = req.get(self.bucketurl + key)
            if res.status_code != 200:
                self.logger('WARN',
                            'downloading ' + key + ' failed.')
                return
            file.write(res.content)

    def _upload_file(self, token, key, file, params):
        file_path = str(self.localdir / file)
        mime_type = mimetypes.guess_type(file_path)[0]
        # guess_type() return a tuple (mime_type, encoding),
        # only mime_type is needed

        self.logger('INFO', 'uploading: ' + file + ' => ' + key)

        progress = ProgressHandler(self.verbose)
        ret, _ = qiniu.put_file(token, key=key,
                                file_path=file_path,
                                params=params,
                                mime_type=mime_type,
                                check_crc=True,
                                progress_handler=progress)
        assert ret['key'] == key

        future = time.time() + 10  # sec since Epoch
        os.utime(file_path, times=(future, future))
        # reset the atime and mtime in the future so that the file doesn't
        # trigger the download criteria (remote ts > local ts)


class QiniuFlatBackup(QiniuBackup):
    """
    This version of Qiniu Backup assumes the local folder is empty
    """

    def __init__(self, options, auth, logger=None,
                 encoding_func=lambda s: s.replace('/', '%2F'),
                 decoding_func=lambda s: s.replace('%2F', '/')):
        super(QiniuFlatBackup, self).__init__(options, auth, logger)
        self.encoding = encoding_func
        self.decoding = decoding_func

    def _list_local_files(self):
        def detect_dir(path):
            if path.is_dir():
                self.logger('ERROR', "subdirectory is detected in a "
                            "flat structure. Please review local file system "
                            "or program setting. Exit now.")
                sys.exit(1)
            else:
                return True

        return {self.decoding(str(file.relative_to(self.localdir))):
                file.stat().st_mtime
                for file in self.localdir.iterdir() if detect_dir(file)}

    def _batch_download(self, keylist, big_file_list=None,
                        output_policy=lambda x: x):
        """
        side-effect: batch download list of resources from qiniu bucket
        :except: raises exception if any of the request return an error
        :param keylist: list of keys for downloading
        :param output_policy: callback function that determines the output
                              filename based on the key
        :return None
        """
        if not keylist:
            return

        for key in keylist:
            file = self.encoding(key)
            self.logger('INFO', 'downloading: ' + key + ' => ' + file)

            file = self.encoding(key)
            file_path = str(self.localdir / file)
            with open(file_path, 'wb') as local_copy:
                self._download_file(key, local_copy, big_file_list)

    def _batch_upload(self, filelist):
        """
        same as batch_download but for uploadging, requires authentication
        :param filelist: list of file names (including path) to be uploaded
               filelist is in the *decoded* state
        :return:None
        """
        if not filelist:
            return

        token = self.auth.upload_token(self.bucketname)
        params = {'x:a': 'a'}

        for file in filelist:
            self._upload_file(token, file, self.encoding(file), params)


class MultipleBackupDriver:
    class _SectionProxyProxy(dict):
        def getboolean(self, key, fallback):
            return bool(self.get(key, fallback))

        def getint(self, key, fallback):
            return int(self.get(key, fallback))

    def __init__(self, options, auth, backup_class):
        self.auth = auth
        self.QBackupClass = backup_class

        bucketsnames = [s.strip() for s in options['bucketname'].split(';')]
        bucketurls = [s.strip() for s in Default['bucketurl'].split(';')]
        localdir = [s.strip() for s in Default['local_dir'].split(';')]
        assert len(bucketsnames) == len(bucketurls) == len(localdir)
        verbose = options.getboolean('verbose', fallback=False)
        log = options.getboolean('log', fallback=False)

        self.tasks = []
        for bn, bu, ld in zip(bucketsnames, bucketurls, localdir):
            self.tasks.append(self._SectionProxyProxy(
                {'bucketname': bn,
                 'bucketurl': bu,
                 'local_dir': ld,
                 'verbose': verbose,
                 'log': log}))

        self.logger = EventLogger(verbose=verbose,
                                  log_to_file=log)

    def synch_all(self):
        for task in self.tasks:
            qbackup = self.QBackupClass(task, self.auth, self.logger)
            qbackup.synch()


class EventLogger:
    def __init__(self, verbose=False, log_to_file=False):
        self.logfile = None

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
        else:
            self.log = lambda tag, msg: None

    def __call__(self, tag, msg):
        self.log(tag, msg)

    def __del__(self):
        if self.logfile:
            self.logfile.close()

    @staticmethod
    def format(tag, msg):
        return "{0} [{1}] {2}".format(datetime.datetime.now(),
                                      tag, msg)


class ProgressHandler:
    def __init__(self, display_progress_bar=False):
        self.bar = None
        self.display = display_progress_bar

    def __call__(self, progress, total):
        if not self.display:
            return

        if not self.bar:
            self.bar = progressbar.ProgressBar(widgets=[
                progressbar.Percentage(), progressbar.Bar()
            ], maxval=total).start()
        self.bar.update(progress)
        if progress >= total:
            self.bar.finish()


if __name__ == '__main__':
    import configparser

    CONFIG = configparser.ConfigParser()
    if not CONFIG.read('config.ini'):
        print(EventLogger.format('ERR', 'could not read config file!'))
        sys.exit(1)

    Default = CONFIG['DEFAULT']

    my_auth = qauth.get_authentication()
    multibackup = MultipleBackupDriver(Default, my_auth, QiniuFlatBackup)
    multibackup.synch_all()
