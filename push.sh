cp ~/local/share/config/digikamrc .

rsync --progress --archive --hard-links --update --delete-after \
    --no-inc-recursive --itemize-changes \
    --exclude thumbnails-digikam.db \
    "./$1" "mustang::Pictures/$1"
