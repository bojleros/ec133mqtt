# Linearization

## Why do we need an linearization

EC133 is a PWM chopper. Brightness of leds is somewhat proportional to the logarythm of Voltage.
Without linearization it would be more difficult to obtain desired brightness.

You can use gnuplot to help yours self with parameters:

```
set term x11 enhanced font "terminal-14"
set xrange [0:255]
set yrange [0:255]
range=255
tau=0.5;
offset=0.05
f(x) = range*(1-offset)*exp(-(1-(x/range))/(0.3)) + range*offset
plot f(x) with lines
tau=0.1
f(x) = range*(1-offset)*exp(-(1-(x/range))/tau) + range*offset ; replot
```
