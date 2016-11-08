#! /usr/bin/env python3

import os
import os.path
import shutil
from rename_pictures import rename_picture

class Opts:
    pass


import logging
log_format= "%(asctime)s %(name)16s:%(lineno)-4d (%(funcName)-21s) %(levelname)-8s %(message)s"
logging.basicConfig (level=logging.INFO, format=log_format)
logger= logging.getLogger ("workflow")

# SD -> 01-tmp
def import_files(move=True):
    if move:
        op = shutil.move
    else:
        op = shutil.copy

    # TODO: put paths in config file
    for root, dirs, files in os.walk('/home/mdione/media/Nikon D7200/DCIM/'):
        for file in files:
            src = os.path.join(root, file)
            dst = os.path.join('/home/mdione/Pictures/incoming/01-tmp', file)

            logger.info("%s -> %s", src, dst)
            op(src, dst)


# NKN_XXX -> date based
# TODO: paths in rename_pictures to config file
def rename():
    opts = Opts()
    opts.dry_run = False

    for root, dirs, files in os.walk('/home/mdione/Pictures/incoming/01-tmp'):
        for file in sorted(files):
            rename_picture(os.path.join(root, file), opts)


# Tag -> 02-new/foo


def main ():
    import_files()
    rename()

if __name__ == '__main__':
    main()
