import utime
from machine import Pin, SPI, PWM, ADC
import utils
import max7219
import sensors
import sys
from esp32_gpio_lcd import GpioLcd


class Devices:
    def __init__(self):
        self.lcd = None
        self.servo = None
        self.display = None
        self.adc = None
        self.button = None
        self.thermometer = None

        if int(utils.get_config("servo_pin", -1)) > -1:
            self.servo_pin = Pin(int(utils.get_config("servo_pin", 4)))
            self.servo = PWM(self.servo_pin, freq=50)

        if int(utils.get_config("display_pin", -1)) > -1:
            if sys.platform == 'esp32':
                self.spi = SPI(1, baudrate=10000000, polarity=1, phase=0, sck=Pin(14), mosi=Pin(13))
            else:
                self.spi = SPI(1, baudrate=10000000, polarity=0, phase=0)
            self.display_pin = Pin(int(utils.get_config("display_pin", 15)), Pin.OUT)
            self.display = max7219.Matrix8x8(self.spi, self.display_pin, 1)
            self.display.brightness(0)
            self.display.fill(0)
            self.display.show()
        if int(utils.get_config("lcd_enable_pin", -1)) > -1:
            self.lcd = GpioLcd(rs_pin=Pin(int(utils.get_config("lcd_rs_pin", 23))),
                               enable_pin=Pin(int(utils.get_config("lcd_enable_pin", 19))),
                               d4_pin=Pin(int(utils.get_config("lcd_d4_pin", 5))),
                               d5_pin=Pin(int(utils.get_config("lcd_d5_pin", 18))),
                               d6_pin=Pin(int(utils.get_config("lcd_d6_pin", 21))),
                               d7_pin=Pin(int(utils.get_config("lcd_d7_pin", 22))),
                               num_lines=2, num_columns=16)
            self.lcd.clear()

        if int(utils.get_config("button_pin", -1)) > -1:
            self.button = Pin(int(utils.get_config("button_pin", 5)), Pin.IN, Pin.PULL_UP)
        if int(utils.get_config("adc_pin", -1)) > -1:
            if sys.platform == 'esp8266':
                self.adc = ADC(int(utils.get_config("adc_pin", 0)))
            elif sys.platform == 'esp32':
                self.adc = ADC(Pin(int(utils.get_config("adc_pin", 2))))
                self.adc.atten(ADC.ATTN_11DB)
                self.adc.width(ADC.WIDTH_10BIT)

        if int(utils.get_config('thermometer_pin', -1)) > -1:
            self.thermometer = sensors.Sensory()

    def write_display(self, fld, val):
        if self.display is not None:
            self.display._write(fld, val)

    async def move_servo(self, val):
        if self.servo is not None:
            self.servo.duty(val)

    def button_value(self):
        if self.button is not None:
            return self.button.value()
        else:
            return 1

    def joy_val(self):
        if self.adc is not None:
            return self.adc.read()
        else:
            return 0

    async def thermometer_value(self, to_history=False):
        t = 0
        if self.thermometer is not None:
            t = await self.thermometer.pomiar_temperatury(to_history)
        return t

    async def display_temperature(self):
        t = await self.thermometer_value()
        self.led_write_number(int(round(t * 10)), 5, [2])

    def led_write_number(self, val, move=0, dots=None):
        if self.display is None:
            return

        if val is not None and val < 0:
            val *= -1
            self.display._write(8 - move, 1)
            move += 1

        if dots is None:
            dots = []
        digits = {1: 48, 2: 109, 3: 121, 4: 51, 5: 91, 6: 95, 7: 112, 8: 127, 9: 123, 0: 126}
        values = []
        if val is None:
            values = [0]
        elif val == 0:
            values = [126]
        else:
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
            self.display._write(pos, d)
            pos -= 1
            i -= 1

    def write_lcd(self, text):
        if self.lcd is not None:
            self.lcd.clear()
            utime.sleep_ms(10)
            self.lcd.putstr(text)

    def write_lcd_at_pos(self, text, x, y):
        if self.lcd is not None:
            self.lcd.move_to(x, y)
            self.lcd.putstr(text)
