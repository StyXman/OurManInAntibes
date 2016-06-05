rsync --progress --archive --hard-links --update --delete-after \
    --exclude thumbnails-digikam.db \
    "./$1" "192.168.0.42::Pictures/$1"
