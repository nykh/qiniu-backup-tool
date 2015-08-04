# Qiniu Backup tool

This tool is developed for my internship at YewWah. Many YewWah resources are uploaded to and managed from a **Qiniu (TM) bucket**, a Chinese cloud service much like Dropbox, but supporting external link. This application perform incremental backup of (possibly multiple) Qiniu buckts.

## Install

clone the file to local directory

`git clone https://github.com/nykh/qiniu-backup-tool.git`

Modify **config.ini** for your own application. Each Qiniu bucket comes with a Name, an URL address (found at 空间设置->域名设置). You should specify the Name, URL, and the Local Directory you wish the bucket to synch with as a triple in the config file. If you wish to synch multiple buckets, concatenate them with `;` in the form below

> bucketname = BucketA; BucketB; BucketC;...
> bucketurl = http://bucketA/; http://bucketB/; http://bucketC/;...
> local_dir = A; B; C

