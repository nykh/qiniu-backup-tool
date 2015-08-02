#  Qiniu Bucket Backup Tool application note

Since the program is mostly completed, it is now time to consider appying on the real world situation. Derek has previously written a Java program that do the same thing and in fact had already backed-up the majority of bucket content online. The problem is now how to make the Qiniu auto-backup tool developed thus far work with the downloaded data.

Because time is money (the last download took 4 days to run), and network traffic costs money (from Qiniu), we certainly do not want to see redundant download/upload.

## Problem

### Windows path convention

Because Windows pathname uses "\" instead of "/" as in POSIX path. This creates major confusion as every key that has "/" in it is treated differently in the POSIX system and Windows.

#### Description of Windows bug

The behavior of the program under Windows machine with a local file `a\b.txt` (remote key `a/b.txt`) is as follows: the program cannot understand that the remote key is the same as the local file path, and a download and upload will occur. This creates another remote copy with key `a\b.txt`. Next time, both copies are downloaded, but written to the same file. The program should be modified to work under this situation without the bug.

### File system hierarchy

Derek's program used a different solution to my program, which is to treat the whole pathname string as the filename. This is **imcompatible** with my solution, which translates it into a file hierarchy.

Either the program should be fundamentally rewritten to work with the flat model, or a method should be developed to (preferably automatically) process the downloaded file and translate their pathname into a hierarchy.

### key name corner cases

Some rules I have discovered about special character on Qiniu key generation

| key | url |  POSIX  | Windows
|--------|--------|
| 中文 | 中文 | 中文 | 中文 |
| :             | :   | :       | :   |
| .             | .   | .       | .   |
| \             | %5C | \       | dir |
| /             | /   | dir     | dir |
| begins with \ | \  | \        |  **silent bug**  |
| begins with / | @/  | **bug** |  **silent bug**  |
| @             | @@  | @       |  @  |

As we can see the most problematic case is when the key begins with a '/' or '\' character. Under Windows, when a key begins with either of these characters, the file is still downloaded, but not to the folder, but to the root of the Device. (ie. `C:/` etc). Under POSIX system, a key that begins with '/' will send the file to the root directory `/`, and of course it will fail because of permission error. These two corner cases need to be dealt with. Perhaps, the solution by Qiniu itself can give us inspiration. Because a url can never contain double slash "//", it automatically inserts a **@** character in front of the first '/'. Perhaps in my program, I can also creaate a `@` directory and put everything that begins with '/' inside there, as long as the key and filepath maintain a bijection.

## Solution

