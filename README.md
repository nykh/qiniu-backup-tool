# Qiniu Bucket Auto-backup tool

## Problem Statement (Phase 1)

Many YewWah resources are uploaded to and managed from a **Qiniu (TM) bucket**, a Chinese cloud service much like Dropbox, but supporting external link. For security, we would like to be able to **periodically** and **incrementally** backup the content of the buckts. The period is typically once per week. "Incrementally" means each backup should only download new or modified files compared to the last backup, so that the system does not need to download the whole bucket each time, which has a size of about 10GB.

The program should utilize the Qiniu API. Initial version only needs to work with a single **public bucket**, which requires no authentification and has the benefit that each file has a permanent URL address.

The program should be easily customizable so that it takes minimum effort to use the program on different bucket.

### Constraint

Time scale is about one week.

## Implementation plan

The **Qiniu python SDK** provides convenient interface for checking status and list the files in the bucket. The API however requires the program to supply the **access_key** and **secret_key** which should never be revealed to the public. I choose to store the authentication keys in a local files, preferably encrypted. Each time the program needs to list the files on the bucket list it can read the authentication keys from the file.

Because we would like to perform **incremental backup**, the program must filter out the files that already exist on the local drive. There are two ways to keep track of the files. The first approach is perhaps easier to implement, which is to store the keys and timestamp as a key-value pair on a local database. Python provides library such as *dbm* or *shelve* that allow us to use such databases with the convenience of a native *dict* object. The second approach is to traverse the local file system and cross out each file whose (current or later) version already exist on the local drive. This has the benefit that if a file is removed locally by purpose or mistake it can be restored by the backup, regardless of what is stored in a database. Python also has relatively convenient library **os** and **pathlib** to traverse a local directory. Because of this benefit, I choose to use the second approach, traversing the local drive each time I need to compare.

To separate parameters data and program itself, I use the **configparser** library to parse a **config.ini** file.

## Problem Statement (Phase 2)

Next, modify the program so that the update works both way. If there is a file on the local drive that is not on the cloud, we would like to **upload** such files. This will require the upload part in the Qiniu API.

Another problem we encountered during testing was that python does not easily handle '/' character in the Qiniu key.

## Implentation Plan

### Local file structure

The Qiniu cloud file system model is different from POSIX file system in that it is totally flat. Even though a key string (eg. 'dir/example') looks like a path, it dows not imply there is a directory 'dir'. However when we download the resource to UNIX system, it does not allow us to have file name with '/'. Here we have two choices: flat or hierarchy. We can translate '/' to some other character and thus prevent the error, or we can translate it into real path, creating directories if such exists.

I choose to implement it with hierarchy because this way it can be more intuitive to navigate the files.

### Version Control

The problem once we have bidirectional synchronization is how to determine whether to upload/download a file. We can consider a naive categorization. On the Wenn's graph shown below, the two easy cases: Files that exist remotely but not locally should be downloaded, and vice versa. However, the more complicate situation is when the same file exist on the remote server and local server, since then there is a problem of version control.

During Phase One, I used a simple criterion, comparing the upload tnime of the remote version and the last modified time of the local one. If the upload time on the remote version is **later** than the last modified time of the local file, then we can be sure the local copy is old and should be updated. However, the other way is more complicated. Because Qiniu Cloud drive is just for uploading, it does not allow editing a file (except renaming, which will be addressed later). This simplified the problem. But if a file's last modified time is later than the upload time, we can not be sure if the file is just downloaded at the last modified time and never touched, or if the file has been editted locally.

If I want to solve this problem, I think I will have to introduce a database that logs the download timestamp of each local file. If the local file has been modified, its timestamp will be later than the one in the database. However, considering this project is for **backup** purpose, I choose to leave out this feature during Phase Two. If a local file has a newer timestamp, the program will just considered it to be the same as the remote copy and no transfer will occur.

### Renaming problem

## Phase 2 Progress

#### issue: redundant download

A minor issue encountered during the implementation of Phase 2 was that when a file is uploaded from local to remote, its remote timestamp is unfortunately going to be later than the local. So next time when the program is run, it will look like the local file is an old version and download again. This is waste of time and resources we want to prevent. A solution is to use the **os.utime** method to set the ST_MTIME timestamp to a time slightly in the future (I chose 10 sec), such that the local mtime is still later than the remote upload time.