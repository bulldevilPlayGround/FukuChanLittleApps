#!/bin/bash
echo "---------remove last build files---------"
rm build dist main.spec *.7z -rf
echo "---------Invoke pyinstaller---------"
pyinstaller --noconsole -i icon.ico -F main.py
#pyinstaller -i icon.ico -F main.py
#echo "---------Compress build files---------"
#7z a "FukuChanToolBox_$(date "+%Y%m%d%H%M%S").7z" build dist


