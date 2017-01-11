#! /usr/bin/env python3

import os
import os.path
import shutil

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap

from rename_pictures import rename_file

import logging
logger= logging.getLogger ("workflow")

# SD -> 01-tmp
def import_files(src_dir, dst_dir, move=True):
    imported= []

    if move:
        op = shutil.move
    else:
        op = shutil.copy

    # TODO: put paths in config file
    for root, dirs, files in os.walk(src_dir):
        for file in files:
            src = os.path.join(root, file)
            dst = os.path.join(dst_dir, file)

            logger.info("%s -> %s", src, dst)
            op(src, dst)
            imported.append (dst)

    return imported


# NKN_XXX -> date based
# TODO: paths in rename_pictures to config file
def rename():
    opts = Opts()
    opts.dry_run = False

    for root, dirs, files in os.walk('/home/mdione/Pictures/incoming/01-tmp'):
        for file in sorted(files):
            rename_file(os.path.join(root, file))


def main ():
    import_files('/home/mdione/media/Nikon D7200/DCIM/',
                 '/home/mdione/Pictures/incoming/01-tmp')
    rename()


if __name__ == '__main__':
    app= QApplication ([])

    log_format= "%(asctime)s %(name)16s:%(lineno)-4d (%(funcName)-21s) %(levelname)-8s %(message)s"
    logging.basicConfig (level=logging.INFO, format=log_format)

    main()
