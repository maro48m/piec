from machine import Pin, SPI, PWM, ADC
import utils
import max7219
import sensors


class Devices:
    def __init__(self):
        if int(utils.get_config("servo_pin", -1)) > -1:
            self.servo_pin = Pin(int(utils.get_config("servo_pin", 4)))
            self.servo = PWM(self.servo_pin, freq=50)

        if int(utils.get_config("display_pin", -1)) > -1:
            self.spi = SPI(1, baudrate=10000000, polarity=0, phase=0)
            self.display_pin = Pin(int(utils.get_config("display_pin", 15)), Pin.OUT)
            self.display = max7219.Matrix8x8(self.spi, self.display_pin, 1)
            self.display.brightness(0)
            self.display.fill(0)
            self.display.show()

        if int(utils.get_config("button_pin", -1)) > -1:
            self.button = Pin(int(utils.get_config("button_pin", 5)), Pin.IN, Pin.PULL_UP)

        self.adc = ADC(0)

        if int(utils.get_config('thermometer_pin', -1)) > -1:
            self.thermometer = sensors.Sensory()

    def write_display(self, fld, val):
        if self.display is not None:
            self.display._write(fld, val)

    def move_servo(self, val):
        if self.servo is not None:
            self.servo.duty(val)

    def button_value(self):
        if self.button is not None:
            return self.button.value()
        else:
            return 1

    def joy_val(self):
        return self.adc.read()

    def thermometer_value(self, to_history=False):
        t = 0
        if self.thermometer is not None:
            t = self.thermometer.pomiar_temperatury(to_history)
        return t

    def display_temperature(self):
        t = self.thermometer_value()
        self.led_write_number(int(round(t * 10)), 5, [2])

    def led_write_number(self, val, move=0, dots=None):
        if dots is None:
            dots = []
        digits = {1: 48, 2: 109, 3: 121, 4: 51, 5: 91, 6: 95, 7: 112, 8: 127, 9: 123, 0: 126}
        values = []
        while val > 0:
            d = int(val % 10)
            val = int(val / 10)
            v = digits[d]
            values.append(v)
        values.reverse()
        pos = 8 - move
        i = len(values)
        for d in values:
            if dots.count(i) > 0:
                d += 128
            if self.display is not None:
                self.display._write(pos, d)
            pos -= 1
            i -= 1