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
        # ISO 8601
        f= date.isoformat ()
        # windows does not support : in filenames
        f= f.replace (':', '.')

        ext= os.path.splitext (src)[1].lower ()

        if opts.destination is None:
            # 'inplace' rename
            opts.destination= os.path.dirname (src)

        dst= os.path.join (opts.destination, "%s%s" % (f, ext))

        if dst==src:
            print "skipping %s: already in good format" % src
            return

        moved= False
        count= 1

        while not moved:
            try:
                ds= os.stat (dst)
            except OSError, e:
                if e.errno!=errno.ENOENT:
                    print "[E:%d] %s" % (e.errno, dst)
                    return
                moved= True
            else:
                print "[W:%s]: %s exists" % (src, dst)
                dst= os.path.join (opts.destination, "%s_%02d%s" % (f, count, ext))
                count+= 1

        print "%s -> %s" % (src, dst)
        try:
            if not opts.dry_run:
                os.rename (src, dst)
        except OSError, e:
            print e, src

    else:
        print "can't find file's date, skipping..."

parser= argparse.ArgumentParser ()
parser.add_argument ('-s', '--source', required=True)
parser.add_argument ('-d', '--destination', default=None)
parser.add_argument ('-p', '--in-place', action='store_true', default=False)
parser.add_argument ('-t', '--on-date', action='store_true', default=False,
                     help='sort files in directories called YYYY/MM-DD')
parser.add_argument ('-m', '--use-mtime', action='store_true', default=False,
                     help="use file's mtime instead of other metadata.")
parser.add_argument ('-n', '--dry-run', action='store_true', default=False)
opts= parser.parse_args (sys.argv[1:])

if stat.S_ISREG (os.stat (opts.source).st_mode):
    rename_picture (opts.source, opts)
else:
    for dirpath, dirnames, filenames in os.walk (opts.source):
        for filename in sorted (filenames):
            src= os.path.join (dirpath, filename)

            rename_picture (src, opts)
