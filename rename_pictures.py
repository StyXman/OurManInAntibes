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
import logging

from gi.repository import GExiv2, GLib

log_format= "%(asctime)s %(name)16s:%(lineno)-4d (%(funcName)-21s) %(levelname)-8s %(message)s"
logging.basicConfig (level=logging.INFO, format=log_format)
logger= logging.getLogger ("rename")


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
            logger.warning ("could not read EXIF date for %s" % file_name)
            return None

    # '2016:07:17 16:46:04'
    try:
        return datetime.strptime (date, '%Y:%m:%d %H:%M:%S')
    except ValueError:
        logger.warning ("could not parse EXIF date for %s: %s" % (file_name, date))
        return None


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


def build_filename (root, base_name, count, ext):
    if count is not None:
        base_name= "%s_%02d" % (base_name, count)

    return os.path.join (root, base_name)+ext


def is_free (src, dst):
    free= False
    ss= os.stat (src)

    try:
        ds= os.stat (dst)
    except OSError as e:
        if e.errno!=errno.ENOENT:
            print ("[E:%d] %s" % (e.errno, dst))
            raise

        # dst is free to take
        free= True
    else:
        # the dst exists, but aren't we just renaming on ourselves?
        # that is, is the filename already in format?
        if ds.st_ino!=ss.st_ino:
            print ("[W:%s]: %s exists" % (src, dst))
        else:
            # it's the same file, so let's get out of here
            # technically it's not free, but this ends the outer loop
            # (see rename_picture())
            free= True

    return free


def rename_picture (src, dry_run=False):
    date= read_image_date (src)

    if date is None:
        # try it as video:
        date= read_video_date (src)

    if not isinstance (date, datetime):
        print ("%s: bad date field format (%r)" % (src, date))
        date= None

    if date is not None:
        # we do two things here
        src_dir, src_name= os.path.split (src)
        ext= os.path.splitext (src_name)[1].lower ()

        # first, we rename the file from src/DSC_XXXX.JPG to a date based name
        # like src/2016-04-30T12.59.40.jpg
        # notice src_dir is equal to dst_dir

        # variant (!!!; see https://xkcd.com/927/) of ISO 8601 compatible with Windows
        # .%f ignored because it's always 0
        # TODO: put in config file
        file_name_format= "%Y-%m-%dT%H.%M.%S"

        dst_dir= src_dir
        # does not include extension
        dst_base_name= date.strftime (file_name_format)

        # then we also link it in the by_date dir
        # TODO: put paths in config file
        dst_by_date_dir= date.strftime ("ByDate/%Y/%m")

        # dst_dir is also src_dir, so we know it already exists :)
        os.makedirs (dst_by_date_dir, exist_ok=True)

        free_dst= False
        free_dst_by_date= False
        count= None

        while not free_dst and not free_dst_by_date:
            dst = build_filename (dst_dir, dst_base_name, count, ext)
            dst_by_date = build_filename (dst_by_date_dir, dst_base_name, count,
                                          ext)

            # check dst does not exist or is the same file
            free_dst= is_free (src, dst)
            # now dst_by_date
            free_dst_by_date= is_free (src, dst_by_date)
            if count is None:
                count= 1
            else:
                count+= 1

        if dst!=src:
            try:
                print ("%s -> %s" % (src, dst))
                if not dry_run:
                    os.rename (src, dst)
            except OSError as e:
                print (e, src)
        else:
            print ("%s already in good format, not renaming." % src)

        # now the date based link uses the same dst_name for consistency
        try:
            print ("%s => %s" % (dst_by_date, dst))
            if not dry_run:
                os.link (dst, dst_by_date)
        except OSError as e:
            print (e, dst)
        else:
            return dst

    else:
        print ("can't find file's date, skipping...")


if __name__=='__main__':
    parser= argparse.ArgumentParser ()
    parser.add_argument ('-n', '--dry-run', action='store_true', default=False)
    parser.add_argument ('sources', metavar='FILE_OR_DIR', nargs='*',
                        default=glob ('incoming/01-tmp/*'))
    opts= parser.parse_args (sys.argv[1:])

    for src in opts.sources:
        try:
            s= os.stat (src)
        except FileNotFoundError:
            print ("%s: File not found" % src)
        else:
            if stat.S_ISREG (s.st_mode):
                rename_picture (src, opts.dry_run)
            else:
                # BUG: it could be something else..
                for dirpath, dirnames, filenames in os.walk (src):
                    # sorting them by name helps resolving same second conflicts
                    for filename in sorted (filenames):
                        f= os.path.join (dirpath, filename)

                        rename_picture (f, opts.dry_run)
