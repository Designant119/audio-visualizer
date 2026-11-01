#!/bin/bash
cd /home/user/Doubao/chats/38441342424762882/visualizer
TOTAL=3603
SEG=360
for i in $(seq 0 9); do
  s=$((i*SEG))
  e=$((s+SEG))
  if [ $e -gt $TOTAL ]; then e=$TOTAL; fi
  echo "=== SEG $i: frames $s-$e ==="
  python3 render_worker_v39.py part_v39_${i}.mp4 $s $e 42 2>&1 | tail -1
  sleep 8
done
echo "=== ALL SEGMENTS DONE ==="
