#! /bin/bash

for src_dir in "${HOME}/media/NIKON D90/DCIM/"*; do
    # * is not expanded if inside ""
    rsync --verbose --archive --remove-source-files \
        "$src_dir/" "incoming/01-tmp/"
done

# ./rename-pictures.py
echo "Now filter out all bad pictures and the run:"
echo './rename-pictures.py'
