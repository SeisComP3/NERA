#!/bin/sh

# specify event id's on the command line

#. $HOME/.seiscomp3/env.sh

proc=geofon-proc.gfz-potsdam.de
acqu=geofon-acqui2.gfz-potsdam.de

db="mysql://yourUser:yourPassword@$proc/seiscomp3"
#ii="combined://$acqu:18000;$acqu:18001"

# scxmldump -I -o inventory.xml -d "$db"

for evt in "$@"
#for evt in gfz2009tdkv gfz2010tcda gfz2011bgpj gfz2011ndhh gfz2012fpsm gfz2012qvak gfz2012xzqz gfz2010avtm gfz2010uxkl gfz2011esoc gfz2011uqry gfz2012fzfa gfz2012rcyo gfz2012yfum gfz2010gtdx gfz2010yxrq gfz2011ewla gfz2011ykjq gfz2012hdex gfz2012rmfw gfz2010nynk gfz2010zerl gfz2011gukd gfz2012arwj gfz2012hdja gfz2012tgbb gfz2010pnyc gfz2011axdw gfz2011mgdu gfz2012chmz gfz2012pxdq gfz2012veem gfz2013ahzu gfz2013gryc gfz2013hpom gfz2013kbsi gfz2013ntiy gfz2013sswo gfz2013uejt gfz2013wniy gfz2013cnwn gfz2013hkrc gfz2013kats gfz2013nfbw gfz2013qzot gfz2013svci gfz2013uxyk
do
    ii="/home/javier/temp/events/$evt.mseed"
    debug=--debug
    ./scxxlmag-compute.py --dump-waveforms --inventory-db "$db" $debug --blacklist blacklist.txt -I "$ii" -d "$db" -H $proc -E "$evt" >$evt.evid || continue
done
