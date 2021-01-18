import esp
import sys
import machine

esp.osdebug(None)

if sys.platform == 'esp32':
    machine.freq(240000000)
else:
    machine.freq(160000000)
