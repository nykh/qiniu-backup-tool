# Qiniu Bucket Auto-backup tool

## Problem Statement

Many YewWah resources are uploaded to and managed from a **Qiniu (TM) bucket**, a Chinese cloud service much like Dropbox, but supporting external link. For security, we would like to be able to **periodically** and **incrementally** backup the content of the buckts. The period is typically once per week. "Incrementally" means each backup should only download new or modified files compared to the last backup, so that the system does not need to download the whole bucket each time, which has a size of about 10GB.

The program should utilize the Qiniu API. Initial version only needs to work with a single **public bucket**, which requires no authentification and has the benefit that each file has a permanent URL address.

The program should be easily customizable so that it takes minimum effort to use the program on different bucket.

### Constraint

Time scale is about one week.

## Implementation plan

- Python 3
- Qiniu python SDK