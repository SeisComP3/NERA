#!/bin/bash

# Use gnuplot to draw the evolution of the magnitude and rupture duration

FILES=*.evid
for f in $FILES
do
	echo "Processing file $f"
	fn="${f%.*}"
	echo "set terminal postscript eps enhanced color font 'Helvetica,10'; set output '$fn.eps'; set xlabel 'Seconds since event time'; set ylabel 'Magnitude M_W(mBc)'; set y2label 'Duration (seconds)'; set title '$f'; set yrange [3:9.2]; set y2range [0:120]; set key left top; set ytics nomirror; set y2tics; plot '$f' using 2:(1.22*\$3-2.11) with lines title 'Magnitude', '$f' using 2:4 with lines title 'Duration' axes x1y2" | gnuplot
done
