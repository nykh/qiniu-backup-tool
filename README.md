# Qiniu Bucket Auto-backup tool

## Problem Statement

Many YewWah resources are uploaded to and managed from a **Qiniu (TM) bucket**, a Chinese cloud service much like Dropbox, but supporting external link. For security, we would like to be able to **periodically** and **incrementally** backup the content of the buckts. The period is typically once per week. "Incrementally" means each backup should only download new or modified files compared to the last backup, so that the system does not need to download the whole bucket each time, which has a size of about 10GB.

The program should utilize the Qiniu API. Initial version only needs to work with a single **public bucket**, which requires no authentification and has the benefit that each file has a permanent URL address.

The program should be easily customizable so that it takes minimum effort to use the program on different bucket.

### Constraint

Time scale is about one week.

## Implementation plan

The **Qiniu python SDK** provides convenient interface for checking status and list the files in the bucket. The API however requires the program to supply the **access_key** and **secret_key** which should never be revealed to the public. I choose to store the authentication keys in a local files, preferably encrypted. Each time the program needs to list the files on the bucket list it can read the authentication keys from the file.

Because we would like to perform **incremental backup**, the program must filter out the files that already exist on the local drive. There are two ways to keep track of the files. The first approach is perhaps easier to implement, which is to store the keys and timestamp as a key-value pair on a local database. Python provides library such as *dbm* or *shelve* that allow us to use such databases with the convenience of a native *dict* object. The second approach is to traverse the local file system and cross out each file whose (current or later) version already exist on the local drive. This has the benefit that if a file is removed locally by purpose or mistake it can be restored by the backup, regardless of what is stored in a database.