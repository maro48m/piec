import esp
import sys
import machine

esp.osdebug(None)
# esp.osdebug(1)

if sys.platform == "esp32":
    machine.freq(240000000)
else:
    machine.freq(160000000)
