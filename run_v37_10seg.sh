#!/bin/bash
cd /home/user/Doubao/chats/38441342424762882/visualizer
declare -a S=("0 380 0" "380 760 1" "760 1141 2" "1141 1521 3" "1521 1902 4" "1902 2282 5" "2282 2662 6" "2662 3043 7" "3043 3423 8" "3423 3804 9")
for seg in "${S[@]}"; do
  set -- $seg
  echo "=== SEG $3: $1-$2 ===" >> v37_10seg.log
  python3 render_worker_v37.py part_v37_$3.mp4 $1 $2 9$3 >> v37_10seg.log 2>&1
  rc=$?
  if [ $rc -ne 0 ]; then
    echo "SEG$3 FAILED rc=$rc, retry" >> v37_10seg.log
    sleep 5
    python3 render_worker_v37.py part_v37_$3.mp4 $1 $2 9$3 >> v37_10seg.log 2>&1
    rc=$?
    [ $rc -ne 0 ] && echo "SEG$3 FAILED AGAIN" >> v37_10seg.log && exit 1
  fi
  echo "SEG$3_DONE" >> v37_10seg.log
  sleep 6
done
echo ALL_SEGS_DONE >> v37_10seg.log
