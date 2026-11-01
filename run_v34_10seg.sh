#!/bin/bash
cd /home/user/Doubao/chats/38441342424762882/visualizer
declare -a S=("951 1331 1" "1331 1712 2" "1712 2092 3" "2092 2472 4" "2472 2853 5" "2853 3233 6" "3233 3614 7" "3614 3804 8")
for seg in "${S[@]}"; do
  set -- $seg
  echo "=== SEG $3: $1-$2 ==="
  python3 render_worker_v34.py part_v34_$3.mp4 $1 $2 5$3
  rc=$?
  if [ $rc -ne 0 ]; then
    echo "SEG$3 FAILED rc=$rc, retry once"
    sleep 5
    python3 render_worker_v34.py part_v34_$3.mp4 $1 $2 5$3
    rc=$?
    [ $rc -ne 0 ] && echo "SEG$3 FAILED AGAIN" && exit 1
  fi
  echo "SEG$3_DONE"
  sleep 8
done
echo ALL_SEGS_DONE
