#!/usr/bin/python

import sys
import os
import glob
import urllib
from xml.dom import minidom

import sitedeploy

lst = glob.glob(os.path.expanduser("~/.sitecopy/*"))
lst.sort()
for s in lst:
    site = os.path.basename(s)
    print "==", site, "=="
    sitedeploy.do_init(site)
    con = sitedeploy.open_db(site)
    c = con.cursor()
    dom = minidom.parse(s)
    items = dom.getElementsByTagName("item")
    for i in items:
        fn = urllib.unquote(
            i.getElementsByTagName("filename")[0].firstChild.data.decode(sitedeploy.FS_ENC)
          )
        _type = i.getElementsByTagName("type")[0].firstChild.tagName
        if _type == "type-file":
            tp = sitedeploy.TYPE_FILE
        elif _type == "type-directory":
            tp = sitedeploy.TYPE_DIR
        else:
            raise ValueError("unknown type: " + _type)
        try:
            perms = int(i.getElementsByTagName("protection")[0].firstChild.data, 8)
        except IndexError:
            perms = 0600
        if tp == sitedeploy.TYPE_FILE:
            mtime = int(i.getElementsByTagName("modtime")[0].firstChild.data)
        else:
            mtime = 0

        c.execute("INSERT INTO remote_items VALUES (?, ?, ?, ?)",
            (fn, tp, perms, mtime))

    con.commit()
    c.close()
    con.close()
