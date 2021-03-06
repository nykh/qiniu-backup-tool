# Qiniu Backup tool  v1.0

This tool is developed for my internship at YewWah. Many YewWah resources are uploaded to and managed from a **Qiniu (TM) bucket**, a Chinese cloud service much like Dropbox, but supporting external link. This application perform **incremental** and **bidirectional** backup of (possibly multiple) Qiniu buckts.

## Install

clone the file to local directory

`git clone https://github.com/nykh/qiniu-backup-tool.git`

or download from the Release tab.

Create a **config.toml** for your own application. Each Qiniu bucket comes with a Name, an URL address (under `空间设置->域名设置`). You should specify the Name, URL, and the Local Directory you wish the bucket to synch with as a triple in the config file. If you wish to synch multiple buckets, simply add a new `[[bucket]]` section. For example:

```toml
[[buckets]]
bucketname = "BucketA"
bucketurl = "http://bucketA/"
localdir = "A"

[[buckets]]
bucketname = "BucketB"
bucketurl = "http://bucketB/"
localdir = "B"
```

You can find an example of working config.ini in the `example` folder. For more information about TOML syntax, see the [TOML GitHub page](https://github.com/toml-lang/toml).

### key file

You should also prepare a file named `keys` that contains your **access** and **secret key** assigned by Qiniu for your account. The file is simple as follows:

```
access_key: [your access key]
secret_key: [your secret key]
```

==**Warnning:** You should never reveal your keys to others==

### Requirement

This program requires the following Python library to run

- **qiniu** - the official Qiniu API
- **request** - the better HTTP library
- **progressbar** - in particular I used [this one](https://pypi.python.org/pypi/progressbar-latest/2.4). Not sure why there are so many copies of this same library on PyPI.
- **arrow** - the better date/time library

If the local directories don't yet exist they will be created upon the first run of program.

## Use

Now that you have installed all the required library and prepared your key file, simplify run the program

`python __main__.py`

and your local folder will be synched with your Qiniu bucket.

## Options

Beside the bucket and local directory setting, you can also set some behavior in the config file.

### verbose and log file

The **verbose** and **log** option in the config file determines if the program will output message to the console and a log file. The content is the same, except the log file doesn't contain the progress bar. A new log file is created each time option **log** is true, and will bear file name `qbackup-[timestamp].log` where the timestamp is the local time up to second.

###  size threshold

The Qiniu API already has built in chunk transmission for upload and will automatically turn on if a file being uploaded is **bigger than 4MB**. The **size_threshold** option in the config file determines the size threshold for download only, in unit of KB, and can be as low as 2MB (=2048KB). When a file's size is over this threshold, transmission by chunks will activate for the file, and visually there will be a progress bar for this download (if you set **verbose** to true, of course).

### purge

The program will generate temporary database file in a `./tmp/` directory, which contains all the remote files and their sizes. Normally the database file is no longer needed after successful execution and the program will delete them automatically. But you can set this to **False** and leave the database files behind. The database can be used by `example/validate-execution.py` script to check whether local and remote directories are identical.

### size_threshold

The program will begin chunk transmission if the file size is bigger than this value, measured in KB. Because the chunk size is 1MB, the lower bound of this value is two chunks (2MB = 2048 KB)