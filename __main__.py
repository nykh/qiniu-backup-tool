__author__ = 'nykh'

from sys import exit
from configparser import ConfigParser

from qbackup import qauth
from qbackup.qbackup import MultipleBackupDriver, EventLogger
from qbackup.qbackup_scaled import QiniuBackupScaled


CONFIG = ConfigParser()
if not CONFIG.read('config.ini'):
    print(EventLogger.format('ERROR', 'could not read config file!'))
    exit(1)

Default = CONFIG['DEFAULT']

my_auth = qauth.get_authentication()
multibackup = MultipleBackupDriver(Default, my_auth, QiniuBackupScaled)
multibackup.synch_all()
