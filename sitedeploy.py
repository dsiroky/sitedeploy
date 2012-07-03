#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
@author: (dasir.cz) David Siroky
@summary: Remake of sitecopy
"""

import sys
import os
import stat
import getopt
import re
import time
import socket
from ftplib import FTP

try:
    import paramiko
    has_ssh = True
except ImportError:
    has_ssh = False

try:
    from pysqlite2 import dbapi2 as sqlite
except ImportError:
    import sqlite3 as sqlite

from sitelib import *

##########################################################################
# constants
##########################################################################

CONFIG_FILE = "~/.sitedeployrc"
INFO_DIR = "~/.sitedeploy"

##########################################################################
# res
##########################################################################

###### config parsing

def _ln(pat):
    return re.compile(r"^\s*" + pat + r"\s*(#.*)?$")

_txt = "\S+|\"[^\"]+\""

re_empty = _ln("")
re_site = _ln(r"site\s+(%s)" % _txt)
re_server = _ln(r"server\s+(%s)" % _txt)
re_port = _ln(r"port\s+(\d+)")
re_remote = _ln(r"remote\s+(%s)" % _txt)
re_local = _ln(r"local\s+(%s)" % _txt)
re_protocol = _ln(r"protocol\s+(\w+)")
re_username = _ln(r"username\s+(%s)" % _txt)
re_password = _ln(r"password\s+(%s)" % _txt)
re_permissions = _ln(r"permissions\s+(\w+)")
re_exclude = _ln(r"exclude\s+(%s)" % _txt)
re_include = _ln(r"include\s+(%s)" % _txt)

##########################################################################
# class Config
##########################################################################

class Config(object):
    def __init__(self, site):
        self.site = site
        self.server = None
        self.port = None
        self.remote = None
        self.local = None
        self.protocol = "ftp"
        self.username = None
        self.password = None
        self.perms = "ignore"
        self.exclude = []
        self.include = []

##########################################################################
# servers stubs
##########################################################################

class Server(object):
    def __init__(self, cfg):
        self.cfg = cfg

    def send(self, row):
        raise NotImplementedError

    def set_perm(self, row):
        raise NotImplementedError

    def delete(self, row):
        raise NotImplementedError

    def walk(self):
        raise NotImplementedError

    def close(self):
        pass

#######################################################

class ServerFtp(Server):
    FTP_ENC = "ISO-8859-2"
    FTP_SEP = "/"

    re_listing = re.compile(
                  r"(?P<perms>[ldrwx-]+)\s+(\S+)\s+(?P<user>\S+)\s+(?P<group>\S+)" \
                  r"\s+(?P<size>\S+)\s+(?P<mon>\S+)\s+(?P<day>\S+)" \
                  r"\s+(?P<year_or_time>\S+)\s+(?P<name>.+)$"
                )

    def __init__(self, *args, **kwargs):
        Server.__init__(self, *args, **kwargs)
        if self.cfg.port:
            port = self.cfg.port
        else:
            port = 21
        print "connecting to %s:%i..." % (self.cfg.server, port)
        self.srv = FTP()
        self.srv.connect(self.cfg.server, port)
        self.srv.set_pasv(False)
        self.srv.login(self.cfg.username, self.cfg.password)
        self.cmd("CWD %s" % self.cfg.remote)

        self.lines = []

    def cmd(self, cmd):
        self.srv.voidcmd(cmd)

    def send(self, row):
        local_name = os.path.join(self.cfg.local, row[0])

        print "sending %c %s %iB" % (row[1], row[0].encode(TERMINAL_ENC, ),
              fs_size(local_name))

        real_name = row[0].encode(ServerFtp.FTP_ENC).replace(os.sep, self.FTP_SEP)

        if row[1] == TYPE_DIR:
            self.srv.voidcmd("MKD %s" % real_name)
        elif row[1] == TYPE_FILE:
            f = file(local_name, "rb")
            self.srv.storbinary("STOR %s" % real_name, f)
            f.close()

    def set_perm(self, row):
        print "setting perms", row[1], row[0].encode(TERMINAL_ENC, "replace"), oct(row[2])
        self.cmd("SITE CHMOD %03o %s" % (row[2], row[0].replace(os.sep, self.FTP_SEP)))

    def delete(self, row):
        print "deleting", row[1], row[0].encode(TERMINAL_ENC, "replace")

        if row[1] == TYPE_DIR:
            self.cmd("RMD %s" % row[0].replace(os.sep, self.FTP_SEP))
        elif row[1] == TYPE_FILE:
            self.cmd("DELE %s" % row[0].replace(os.sep, self.FTP_SEP))

    def close(self):
        self.srv.close()

    def _perm2oct(self, perms):
        p = 0
        if perms[1] == "r": p |= 0400
        if perms[2] == "w": p |= 0200
        if perms[3] == "x": p |= 0100
        if perms[4] == "r": p |= 040
        if perms[5] == "w": p |= 020
        if perms[6] == "x": p |= 010
        if perms[7] == "r": p |= 04
        if perms[8] == "w": p |= 02
        if perms[9] == "x": p |= 01
        return p

    def _storlines(self, line):
        self.lines.append(line)

    def _walk(self, dir):
        print "/" + dir
      
        self.lines = []
        self.srv.retrlines("LIST " + dir, self._storlines)
        lines = list(self.lines)
        files = []
        subdirs = []
        for l in lines:
            m = ServerFtp.re_listing.match(l)
            if m:
                name = m.group("name")
                perms = m.group("perms")
                if (perms[0] == "d") and (name not in (".", "..")):
                    subdirs.append((name, perms))
                elif perms[0] == "-":
                    files.append((unicode(name, ServerFtp.FTP_ENC),
                                  self._perm2oct(perms), time.time()))

        yield [unicode(dir, ServerFtp.FTP_ENC), 0, time.time(), files]

        for (d, p) in subdirs:
            if dir != "":
                d = dir + "/" + d
            for i in self._walk(d):
                i[1] = self._perm2oct(p)
                yield i

    def walk(self):
        return self._walk("")

#######################################################

class ServerSsh(Server):
    ENC = "ISO-8859-2"

    def __init__(self, *args, **kwargs):
        Server.__init__(self, *args, **kwargs)
        print "connecting to %s..." % self.cfg.server
        hkeys = paramiko.util.load_host_keys(os.path.expanduser("~/.ssh/known_hosts"))
        for host, hkey in hkeys.items():
            if self.cfg.server in host:
                hostkeytype = hkey.keys()[0]
                hostkey = hkey[hostkeytype]
                break
        else:
            print "host is not in known_hosts"
            sys.exit(1)

        if self.cfg.port:
            port = self.cfg.port
        else:
            port = 22
        self.t = paramiko.Transport((self.cfg.server, port))
        self.t.connect(username=self.cfg.username, 
                       password=self.cfg.password, 
                       hostkey=hostkey)
        self.t.use_compression(True)
        self.sftp = paramiko.SFTP.from_transport(self.t)
        self.sftp.chdir(self.cfg.remote)

    def send(self, row):
        local_name = os.path.join(self.cfg.local, row[0])

        print "sending %c %s %iB" % (row[1], row[0].encode(TERMINAL_ENC, "replace"),
              fs_size(local_name))

        if row[1] == TYPE_DIR:
            self.sftp.mkdir(row[0], 0700)
        elif row[1] == TYPE_FILE:
            self.sftp.put(local_name, row[0])

    def set_perm(self, row):
        print "setting perms", row[1], row[0].encode(TERMINAL_ENC, "replace"), oct(row[2])
        self.sftp.chmod(row[0], row[2])

    def delete(self, row):
        print "deleting", row[1], row[0].encode(TERMINAL_ENC, "replace")
        if row[1] == TYPE_DIR:
            self.sftp.rmdir(row[0])
        elif row[1] == TYPE_FILE:
            self.sftp.remove(row[0])

    def close(self):
        self.t.close()

##########################################################################
# functions
##########################################################################

def open_server(cfg):
    try:
        if cfg.protocol == "ftp":
            return ServerFtp(cfg)
        elif cfg.protocol == "ssh":
            return ServerSsh(cfg)
        else:
            print "unknown protocol", cfg.protocol
            sys.exit(1)
    except KeyboardInterrupt:
        raise
    except Exception, e:
        prerr("error:" + str(e))
        sys.exit(1)

#############################################################

def load_config_site(site, f):
    cfg = Config(site)

    for l in f:
        m = None
        for (r, attr) in ((re_server, "server"),
                          (re_remote, "remote"),
                          (re_local, "local"),
                          (re_protocol, "protocol"),
                          (re_username, "username"),
                          (re_password, "password"),
                          (re_permissions, "perms")):
            m = r.match(l)
            if m:
                setattr(cfg, attr, m.group(1))
                break
        if m is not None:
            continue

        m = re_port.match(l)
        if m:
            cfg.port = int(m.group(1))
            continue

        m = re_exclude.match(l)
        if m:
            cfg.exclude.append(m.group(1))
            continue
        
        m = re_include.match(l)
        if m:
            cfg.include.append(m.group(1))
            continue
        
        if re_empty.match(l):
            continue

        if re_site.match(l):
            break

        if m is None:
            print "unknown directive:", l.strip()
            sys.exit(1)

    return cfg
    
#############################################################

def load_config(site):
    cfg = None
    cfg_file = os.path.expanduser(CONFIG_FILE)
  
    try:
        f = file(cfg_file, "r")
        read_site = False
        for l in f:
            m = re_site.match(l)
            if m:
                sname = m.group(1)
                if sname == site:
                    cfg = load_config_site(site, f)
                    break
        f.close()
    except IOError:
        prerr("Can't read config file " + cfg_file)
        sys.exit(1)

    if cfg is None:
        print "Config file doesn't contain desired site."
        sys.exit(1)

    return cfg

#############################################################

def open_db(site, new=False):
    info_dir = os.path.expanduser(INFO_DIR)
    if not os.path.isdir(info_dir):
        os.mkdir(info_dir)

    dbname = os.path.join(info_dir, site + ".db")

    if new:
        try:
            os.unlink(dbname)
        except OSError:
            pass

    con = sqlite.connect(database=dbname, timeout=10.0)
    return con

#############################################################

def _load_locals(cfg, con):
    c = con.cursor()
    c.execute("DELETE FROM local_items")

    if not os.path.isdir(cfg.local):
        print "local mirror doesn't exist"
        return []

    for (_d, subdirs, files) in os.walk(cfg.local):
        d = _d[len(cfg.local):].lstrip(os.sep)
        d = unicode(d, FS_ENC)

        for _subd in list(subdirs):
            subd = os.path.join(_d, _subd)
            subd = subd[len(cfg.local):].lstrip(os.sep)
            subd = unicode(subd, FS_ENC)
            if match_pat(subd, cfg.exclude) and not match_pat(subd, cfg.include):
                subdirs.remove(_subd)

        if d != "":
            c.execute("""INSERT INTO local_items (name, type, perm, mtime) 
                    VALUES (?, ?, ?, ?)""", (d, TYPE_DIR, fs_perms(_d), fs_mtime(_d)))

        for _fn in files:
            _fn = unicode(_fn, FS_ENC)
            fn = os.path.join(d, _fn)
            _fn = os.path.join(_d, _fn)

            if not os.path.isfile(_fn):
                print "unknown file type " + fn
                continue
            if match_pat(fn, cfg.exclude) and not match_pat(fn, cfg.include):
                continue

            c.execute("""INSERT INTO local_items (name, type, perm, mtime) 
                    VALUES (?, ?, ?, ?)""", (fn, TYPE_FILE, fs_perms(_fn), fs_mtime(_fn)))

    con.commit()

#############################################################

def _get_changes(con):
    c = con.cursor()
    c.execute("""SELECT * FROM local_items EXCEPT SELECT * FROM remote_items ORDER BY name""")
    return c.fetchall()

#############################################################

def _get_dels(con):
    c = con.cursor()
    c.execute("""SELECT name FROM remote_items EXCEPT SELECT name FROM local_items ORDER BY name DESC""")
    return c.fetchall()

#############################################################

def need_delete(cfg, local_row, remote_row):
    return (remote_row is not None) and (local_row[1] != remote_row[1])

def need_send(cfg, local_row, remote_row):
    return (remote_row is None) or \
           ((local_row[1] == TYPE_FILE) and (local_row[3] > remote_row[3]))

def need_perms(cfg, local_row, remote_row):
    return (cfg.perms == "all") and \
           ((remote_row is None) or (local_row[2] != remote_row[2]))

#############################################################

def do_init(site):
    cfg = load_config(site)
    con = open_db(site, True)
    c = con.cursor()
    c.execute("""
                CREATE TABLE remote_items (
                    name VARCHAR(255) PRIMARY KEY,
                    type CHAR(1),
                    perm INT DEFAULT 0,
                    mtime INT
                  )
              """)
    c.execute("CREATE INDEX ri ON remote_items(name, type, perm, mtime)")
    c.execute("""
                CREATE TABLE local_items (
                    name VARCHAR(255) PRIMARY KEY,
                    type CHAR(1),
                    perm INT DEFAULT 0,
                    mtime INT
                  )
              """)
    c.execute("CREATE INDEX li ON local_items(name, type, perm, mtime)")
    con.close()
    print "- init done"

#############################################################

def do_list_changes(site):
    cfg = load_config(site)
    con = open_db(site)
    _load_locals(cfg, con)
    
    c = con.cursor()

    for row in _get_dels(con):
        print "x   " + row[0].encode(TERMINAL_ENC, "replace")
    for row in _get_changes(con):
        c.execute("SELECT * FROM remote_items WHERE name=?", (row[0],))
        remote_row = c.fetchone()

        nd = need_delete(cfg, row, remote_row)
        if nd:
            remote_row = None
        ns = need_send(cfg, row, remote_row)
        np = need_perms(cfg, row, remote_row)

        if nd or ns or np:
            print "%c%c%c %s" % \
              (
                {False:" ", True:"x"}[nd],
                {False:" ", True:"s"}[ns],
                {False:" ", True:"p"}[np],
                row[0].encode(TERMINAL_ENC, "replace")
              )

    con.close()

#############################################################

def do_update(site):
    cfg = load_config(site)
    srv = open_server(cfg)

    con = open_db(site)
    _load_locals(cfg, con)
    c = con.cursor()

    ######## delete
    t = time.time()
    for row in _get_dels(con):
        c.execute("SELECT * FROM remote_items WHERE name=?", (row[0],))
        remote_row = c.fetchone()
        try:
            srv.delete(remote_row)
        except KeyboardInterrupt:
            raise
        except Exception, e:
            prerr(str(e))
        else:
            c.execute("DELETE FROM remote_items WHERE name=?", (row[0],))

        t2 = time.time()
        if t2 - t > 0.5:
            t = t2
            con.commit()

    ######## update
    t = time.time()
    for row in _get_changes(con):
        c.execute("SELECT * FROM remote_items WHERE name=?", (row[0],))
        remote_row = c.fetchone()

        try:
            # if the item type differs then delete it first
            done_del = False
            if need_delete(cfg, row, remote_row):
                srv.delete(remote_row)
                remote_row = None
                done_del = True
        except KeyboardInterrupt:
            raise
        except Exception, e:
            prerr(str(e))
        else:
            if done_del:
                c.execute("DELETE FROM remote_items WHERE name=?", (row[0],))

        try:
            # create a new dir or send a modified file
            done_send = False
            if need_send(cfg, row, remote_row):
                srv.send(row)
                done_send = True
        except KeyboardInterrupt:
            raise
        except Exception, e:
            prerr(str(e))
        else:
            if done_send:
                if remote_row is None:
                    perm = row[2]
                else:
                    perm = remote_row[2]
                c.execute("REPLACE INTO remote_items VALUES \
                    (?, ?, ?, ?)", (row[0], row[1], perm, row[3]))

        try:
            # set permissions
            done_perms = False
            if need_perms(cfg, row, remote_row):
                srv.set_perm(row)
                perm = row[2]
                done_perms = True
        except KeyboardInterrupt:
            raise
        except Exception, e:
            prerr(str(e))
        else:
            if done_perms:
                c.execute("UPDATE remote_items SET perm=? WHERE name=?", 
                      (perm, row[0]))

        t2 = time.time()
        if t2 - t > 0.5:
            t = t2
            con.commit()

    con.commit()
    con.close()
    print "- update done"

#############################################################

def do_catchup(site):
    cfg = load_config(site)
    con = open_db(site)
    _load_locals(cfg, con)
    c = con.cursor()
    c.execute("DELETE FROM remote_items")
    c.execute("INSERT INTO remote_items SELECT * FROM local_items")
    con.commit()
    con.close()
    print "- catchup done"


#############################################################

def do_fetch(site):
    cfg = load_config(site)
    srv = open_server(cfg)
    con = open_db(site)
    c = con.cursor()
    c.execute("DELETE FROM remote_items")

    t = time.time()
    for (d, perm, mtime, files) in srv.walk():
        if match_pat(d, cfg.exclude) and not match_pat(d, cfg.include):
            continue

        if d != "":
            c.execute("""INSERT INTO remote_items (name, type, perm, mtime) 
                    VALUES (?, ?, ?, ?)""", (d, TYPE_DIR, perm, mtime))

        for (fn, perm, mtime) in files:
            fn = os.path.join(d, fn)

            if match_pat(fn, cfg.exclude) and not match_pat(fn, cfg.include):
                continue

            c.execute("""INSERT INTO remote_items (name, type, perm, mtime) 
                    VALUES (?, ?, ?, ?)""", (fn, TYPE_FILE, perm, mtime))
        
        t2 = time.time()
        if t2 - t > 0.5:
            t = t2
            con.commit()

    con.commit()
    con.close()
    print "- info fetch done"

#############################################################

def do_remove_from_db(site, pat):
    cfg = load_config(site)
    con = open_db(site)
    c = con.cursor()
    c2 = con.cursor()

    c.execute("SELECT * FROM remote_items")
    for row in c.fetchall():
        if match_pat(row[0], [pat]):
            print row[0].encode(TERMINAL_ENC)
            c2.execute("DELETE FROM remote_items WHERE name=?", (row[0],))
            if row[1] == TYPE_DIR:
                c2.execute("DELETE FROM remote_items WHERE name LIKE ?", 
                    (row[0].replace("%", "%%") + "%",))

    con.commit()
    con.close()

#############################################################

def do_mark_unmodified(site, pat):
    cfg = load_config(site)
    con = open_db(site)
    c = con.cursor()
    c2 = con.cursor()

    c.execute("SELECT * FROM local_items")
    for row in c.fetchall():
        if match_pat(row[0], [pat]):
            print row[0].encode(TERMINAL_ENC)
            c2.execute("REPLACE INTO remote_items VALUES (?,?,?,?)", row)
            if row[1] == TYPE_DIR:
                c2.execute("REPLACE INTO remote_items SELECT * "
                              "FROM local_items WHERE name LIKE ?", 
                    (row[0].replace("%", "%%") + "%",))

    con.commit()
    con.close()

#############################################################

def do_dump(site):
    cfg = load_config(site)
    con = open_db(site)
    _load_locals(cfg, con)
    c = con.cursor()

    print "=== local state ==="
    c.execute("SELECT * FROM local_items")
    for row in c.fetchall():
        txt = u"%c 0%03o %s %s" % (
            row[1],
            row[2],
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row[3])),
            row[0]
          )
        print txt.encode(TERMINAL_ENC, "replace")

    print
    print "=== remote state ==="
    c.execute("SELECT * FROM remote_items")
    for row in c.fetchall():
        txt = u"%c 0%03o %s %s" % (
            row[1],
            row[2],
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row[3])),
            row[0]
          )
        print txt.encode(TERMINAL_ENC, "replace")

    con.close()

#############################################################

def print_help():
    print """
sitedeploy opts sitename
  opts:
    -i        init site
    -l        list changed files (to be deployed)
    -u        update remote site
    -c        catchup
    -f        fetch info from the remote site
    -r pat    remove files (matched by pat) from the state database
    -m pat    mark files (matched by pat) as "unmodified"
    -d        dump state info
"""
    sys.exit(1)

#############################################################

def run():
    try:
        optlist, args = getopt.getopt(sys.argv[1:], "ilucfr:m:d")
    except getopt.GetoptError:
        print_help()

    if len(optlist) == 0:
        print_help()
    if len(args) == 0:
        print_help()

    site = args[0]

    for o, a in optlist:
        if o == "-i":
            do_init(site)
        elif o == "-l":
            do_list_changes(site)
        elif o == "-u":
            do_list_changes(site)
            print "Do update [y/N]?"
            if raw_input().lower() == "y":
                do_update(site)
        elif o == "-c":
            do_catchup(site)
        elif o == "-f":
            do_fetch(site)
        elif o == "-r":
            do_remove_from_db(site, a)
        elif o == "-m":
            do_mark_unmodified(site, a)
        elif o == "-d":
            do_dump(site)

if __name__ == "__main__":
    run()

