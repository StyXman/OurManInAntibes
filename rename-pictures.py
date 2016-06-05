#! /usr/bin/python2

# python2 because pyexiv2 is not on py3 yet

import pyexiv2
import sys
import os
import os.path
from datetime import datetime
import errno
import subprocess
import stat
import argparse
import pdb

# variant (!!!; see https://xkcd.com/927/) of ISO 8601 compatible with Windows
# .%f ignored because it's always 0
# 2016/04/2016-04-30T12.59.40.jpg
file_name_format= "%Y/%m/%Y-%m-%dT%H.%M.%S"

def read_image_date (file_name):
    metadata = pyexiv2.ImageMetadata (file_name)
    try:
        metadata.read ()
    except IOError:
        return None

    try:
        date= metadata['Exif.Photo.DateTimeOriginal'].value
    except KeyError:
        try:
            date= metadata['Exif.Image.DateTime'].value
        except KeyError:
            date= None

    return date

def read_video_date (file_name):
    cmd= 'avprobe -show_format -loglevel quiet'.split ()
    cmd.append (file_name)
    output= subprocess.Popen (cmd, stdout=subprocess.PIPE)

    date= None

    for line in output.stdout:
        if line.startswith ('TAG:creation_time='):
            date= datetime.strptime (line.split ('=')[1], '%Y-%m-%d %H:%M:%S\n')
            break

    return date

def rename_picture (src, opts):
    date= read_image_date (src)

    if date is None:
        # try it as video:
        date= read_video_date (src)

    if not isinstance (date, datetime):
        print "%s: bad date field format (%r)" % (src, date)
        date= None

    if date is not None:
        ext= os.path.splitext (src)[1].lower ()

        dst= date.strftime (file_name_format)+ext
        dst_dir, dst_name= os.path.split (dst)

        try:
            os.makedirs (dst_dir)
        except OSError as e:
            if e.errno==17: # EEXIST
                pass

        if dst==src:
            print "skipping %s: already in good format" % src
            return

        moved= False
        count= 1
        ss= os.stat (src)

        while not moved:
            try:
                ds= os.stat (dst)
            except OSError, e:
                if e.errno!=errno.ENOENT:
                    print "[E:%d] %s" % (e.errno, dst)
                    return

                # dst is free to take
                moved= True
            else:
                # foo= raw_input ('conflict found: %s -> %s; break for inspection [y/N]?' % (src, dst))
                # if foo!='':
                #     pdb.set_trace ()

                if ds.st_size==ss.st_size:
                    print "skipping %s: already in place -> %s" % (src, dst)
                    return

                print "[W:%s]: %s exists" % (src, dst)
                dst= os.path.join (dst_dir, "%s_%02d%s" % (dst_name, count, ext))
                count+= 1

        print "%s -> %s" % (src, dst)
        try:
            if not opts.dry_run:
                os.link (src, dst)
        except OSError, e:
            print e, src

    else:
        print "can't find file's date, skipping..."

parser= argparse.ArgumentParser ()
parser.add_argument ('-s', '--source', default='incoming/01-tmp')
parser.add_argument ('-n', '--dry-run', action='store_true', default=False)
opts= parser.parse_args (sys.argv[1:])

if stat.S_ISREG (os.stat (opts.source).st_mode):
    rename_picture (opts.source, opts)
else:
    for dirpath, dirnames, filenames in os.walk (opts.source):
        # sorting them by name helps resolving same second conflicts
        for filename in sorted (filenames):
            src= os.path.join (dirpath, filename)

            rename_picture (src, opts)
