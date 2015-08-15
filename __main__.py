__author__ = 'nykh'

from sys import exit
import pytoml

from qbackup import qauth
from qbackup.qbackup import EventLogger
from qbackup.qbackup_scaled import QiniuBackupScaled

class MultipleBackupDriver:
    def __init__(self, config, auth, backup_class):
        self.auth = auth
        self.QBackupClass = backup_class

        verbose = config['options'].get('verbose', True)
        log = config['options'].get('verbose', False)
        self.logger = EventLogger(verbose=verbose,
                                  log_to_file=log)
        self.config = config

        self.tasks = []
        for b in self.config['buckets']:
            b.update(self.config['options'])
            self.tasks.append(b)

    def synch_all(self):
        for task in self.tasks:
            qbackup = self.QBackupClass(task, self.auth, self.logger)
            qbackup.synch()

if __name__ == '__main__':
    config = None
    try:
        with open('config.toml') as conffile:
            config = pytoml.load(conffile)
    except:
        print(EventLogger.format('ERROR', 'fail to read config file!'))
        exit(1)

    my_auth = qauth.get_authentication()
    multibackup = MultipleBackupDriver(config, my_auth, QiniuBackupScaled)
    multibackup.synch_all()
