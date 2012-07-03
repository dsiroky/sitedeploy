"""
@author: (dasir.cz) David Siroky
@summary: support routines for site*
"""

import os
import shutil
import stat
import fnmatch
import hashlib
import sys

##########################################################################
# constants
##########################################################################

TERMINAL_ENC = "UTF-8"
FS_ENC = "ISO-8859-2"

TYPE_FILE = "F"
TYPE_DIR = "D"
TYPE_SYMLINK = "S"

##########################################################################
# functions
##########################################################################

def fs_del(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.unlink(path)

#############################################################

def fs_mtime(n):
    st = os.lstat(n)
    return st[stat.ST_MTIME]

#############################################################

def fs_perms(n):
    st = os.lstat(n)
    return st[stat.ST_MODE] & 0777

#############################################################

def fs_type(n):
    if os.path.islink(n):
        return TYPE_SYMLINK
    elif os.path.isdir(n):
        return TYPE_DIR
    elif os.path.isfile(n):
        return TYPE_FILE

    return None

#############################################################

def fs_size(n):
    st = os.lstat(n)
    return st[stat.ST_SIZE]

#############################################################

def match_pat(fn, pat_list, excl_list=None):
    if excl_list:
        for p in excl_list:
            if p.startswith(os.sep):
                _p = p.lstrip(os.sep)
                if fnmatch.fnmatch(fn, _p):
                    return False
            else:
                base = os.path.basename(fn)
                if fnmatch.fnmatch(base, p):
                    return False
        
    for p in pat_list:
        if p.startswith(os.sep):
            _p = p.lstrip(os.sep)
            if fnmatch.fnmatch(fn, _p):
                return True
        else:
            base = os.path.basename(fn)
            if fnmatch.fnmatch(base, p):
                return True
        
    return False

#############################################################

def hash_file(fn):
    h = hashlib.md5()
    f = file(fn, "rb")
    while True:
        buf = f.read(1024*64)
        if len(buf) == 0:
            break
        h.update(buf)
    f.close()
    return h.hexdigest()

#############################################################

def prerr(msg):
    sys.stderr.write(msg + "\n")

