cp ~/local/share/config/digikamrc .

rsync --progress --archive --hard-links --update --delete-after \
    --exclude thumbnails-digikam.db \
    "./$1" "mustang::Pictures/$1"
