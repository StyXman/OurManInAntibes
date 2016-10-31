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
    output= subprocess.Popen (cmd, stdout=subprocess.PIPE,
                              universal_newlines=True)

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

        # first, we rename the file from src/DSC_XXXX.JPG to a date based name
        # like src/2016-04-30T12.59.40.jpg
        # notice src_dir is equal to dst_dir

        # variant (!!!; see https://xkcd.com/927/) of ISO 8601 compatible with Windows
        # .%f ignored because it's always 0
        file_name_format= "%Y-%m-%dT%H.%M.%S"

        # we calculate the dst_name based on a dst_base_name
        # the reason is that later, if the base name already exists,
        # we'll try to find alternative ones based on the base one
        dst_dir= src_dir
        # does not include extension
        dst_base_name= date.strftime (file_name_format)
        # but this one does
        dst_name= dst_base_name+ext
        dst= os.path.join (dst_dir, dst_name)

        # then we also link it in the by_date dir
        dst_by_date_dir= date.strftime ("ByDate/%Y/%m")

        # dst_dir is also src_dir, so we know it already exists :)
        os.makedirs (dst_by_date_dir, exist_ok=True)

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
                # update the dst_name with the count based prefix
                dst_name= "%s_%02d%s" % (dst_base_name, count, ext)
                dst= os.path.join (dst_dir, dst_name)
                count+= 1

        if dst_name!=src_name:
            try:
                print ("%s -> %s" % (src, dst))
                if not opts.dry_run:
                    os.rename (src, dst)
            except OSError as e:
                print (e, src)

        # now the date based link uses the same dst_name for consistency
        dst_by_date= os.path.join (dst_by_date_dir, dst_name)
        if not os.path.exists (dst_by_date):
            try:
                print ("%s => %s" % (dst, dst_by_date))
                if not opts.dry_run:
                    os.link (dst, dst_by_date)
            except OSError as e:
                print (e, dst)

    else:
        print ("can't find file's date, skipping...")


if __name__=='__main__':
    parser= argparse.ArgumentParser ()
    parser.add_argument ('-n', '--dry-run', action='store_true', default=False)
    parser.add_argument ('sources', metavar='FILE_OR_DIR', nargs='*',
                        default=glob ('incoming/01-tmp/DSC*'))
    opts= parser.parse_args (sys.argv[1:])

    for src in opts.sources:
        try:
            s= os.stat (src)
        except FileNotFoundError:
            print ("%s: File not found" % src)
        else:
            if stat.S_ISREG (s.st_mode):
                rename_picture (src, opts)
            else:
                # BUG: it could be something else..
                for dirpath, dirnames, filenames in os.walk (src):
                    # sorting them by name helps resolving same second conflicts
                    for filename in sorted (filenames):
                        f= os.path.join (dirpath, filename)

                        rename_picture (f, opts)
