__author__ = 'nykh'

from sys import exit
from configparser import ConfigParser

from qbackup import qauth
from qbackup.qbackup import EventLogger
from qbackup.qbackup_scaled import QiniuBackupScaled

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
        bucketurls = [s.strip() for s in options['bucketurl'].split(';')]
        localdir = [s.strip() for s in options['local_dir'].split(';')]
        assert len(bucketsnames) == len(bucketurls) == len(localdir)
        verbose = options.getboolean('verbose', fallback=False)
        log = options.getboolean('log', fallback=False)
        purge = options.getboolean('purge', fallback=True)

        self.tasks = []
        for bn, bu, ld in zip(bucketsnames, bucketurls, localdir):
            self.tasks.append(self._SectionProxyProxy(
                {'bucketname': bn,
                 'bucketurl': bu,
                 'local_dir': ld,
                 'verbose': verbose,
                 'log': log,
                 'purge': purge}))

        self.logger = EventLogger(verbose=verbose,
                                  log_to_file=log)

    def synch_all(self):
        for task in self.tasks:
            qbackup = self.QBackupClass(task, self.auth, self.logger)
            qbackup.synch()

if __name__ == '__main__':
    CONFIG = ConfigParser()
    if not CONFIG.read('config.ini'):
        print(EventLogger.format('ERROR', 'could not read config file!'))
        exit(1)

    Default = CONFIG['DEFAULT']

    my_auth = qauth.get_authentication()
    multibackup = MultipleBackupDriver(Default, my_auth, QiniuBackupScaled)
    multibackup.synch_all()
