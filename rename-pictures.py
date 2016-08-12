#! /usr/bin/python3

import sys
import os
import os.path
from datetime import datetime
import errno
import subprocess
import stat
import argparse
from glob import glob

from gi.repository import GExiv2, GLib


def read_image_date (file_name):
    try:
        metadata = GExiv2.Metadata (file_name)
    except GLib.Error:
        return None

    try:
        date= metadata['Exif.Photo.DateTimeOriginal']
    except KeyError:
        try:
            date= metadata['Exif.Image.DateTime']
        except KeyError:
            date= None

        # '2016:07:17 16:46:04'
    return datetime.strptime (date, '%Y:%m:%d %H:%M:%S')

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
        print ("%s: bad date field format (%r)" % (src, date))
        date= None

    if date is not None:
        # we do twothings here
        src_dir, src_name= os.path.split (src)
        ext= os.path.splitext (src_name)[1].lower ()

        # first, we rename the file from DSC_XXXX.JPG to a date based name
        # variant (!!!; see https://xkcd.com/927/) of ISO 8601 compatible with Windows
        # .%f ignored because it's always 0
        # 2016/04/2016-04-30T12.59.40.jpg
        file_name_format= "%Y-%m-%dT%H.%M.%S"
        dst= os.path.join (src_dir, date.strftime (file_name_format)+ext)
        dst_dir, dst_name= os.path.split (dst)

        # then we also link it in the by_date dir
        dst_by_date= date.strftime ("%Y/%m/"+file_name_format)+ext


        os.makedirs (dst_dir, exist_ok=True)

        renamed= False
        count= 1
        ss= os.stat (src)

        while not renamed:
            try:
                ds= os.stat (dst)
            except OSError as e:
                if e.errno!=errno.ENOENT:
                    print ("[E:%d] %s" % (e.errno, dst))
                    return

                # dst is free to take
                renamed= True
            else:
                print ("[W:%s]: %s exists" % (src, dst))
                dst= os.path.join (dst_dir, "%s_%02d%s" % (dst_name, count, ext))
                count+= 1

        try:
            print ("%s -> %s" % (src, dst))
            if not opts.dry_run:
                os.rename (src, dst)

            print ("%s => %s" % (dst, dst_by_date))
            if not opts.dry_run:
                os.link (dst, dst_by_date)
        except OSError as e:
            print (e, src)

    else:
        print ("can't find file's date, skipping...")

parser= argparse.ArgumentParser ()
parser.add_argument ('-n', '--dry-run', action='store_true', default=False)
parser.add_argument ('sources', metavar='FILE_OR_DIR', nargs='*',
                     default=glob ('incoming/01-tmp/DSC*'))
opts= parser.parse_args (sys.argv[1:])

for src in opts.sources:
    if stat.S_ISREG (os.stat (src).st_mode):
        rename_picture (src, opts)
    else:
        for dirpath, dirnames, filenames in os.walk (src):
            # sorting them by name helps resolving same second conflicts
            for filename in sorted (filenames):
                f= os.path.join (dirpath, filename)

                rename_picture (f, opts)
