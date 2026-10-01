"""Read one fixed disposable restore target without following links or writing."""
import hashlib, os, stat
from pathlib import Path

def restored_file(root=Path('/var/lib/ops-lab')):
    path=root/'restore-file.txt'
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except FileNotFoundError:return {'exists':False,'approved_path':'/var/lib/ops-lab/restore-file.txt'}
    except OSError:return {'error':'Restore target cannot be read safely'}
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size>1024*1024:
            return {'error':'Restore target must be a regular file of at most 1 MiB'}
        digest=hashlib.sha256();total=0
        while True:
            block=os.read(fd,65536)
            if not block:break
            total+=len(block)
            if total>1024*1024:return {'error':'Restore target exceeded bounded read size'}
            digest.update(block)
        after=os.fstat(fd)
        try:current=path.lstat()
        except FileNotFoundError:return {'error':'Restore target disappeared during verification'}
        if (current.st_dev,current.st_ino)!=(after.st_dev,after.st_ino):
            return {'error':'Restore target was replaced during verification; retry observed state'}
        if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            return {'error':'Restore target changed during verification; retry observed state'}
        return {'exists':True,'approved_path':'/var/lib/ops-lab/restore-file.txt',
                'sha256':digest.hexdigest(),'mode':format(stat.S_IMODE(after.st_mode),'04o'),'bytes':total}
    finally:os.close(fd)
