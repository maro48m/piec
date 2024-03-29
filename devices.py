import utime
from machine import Pin, PWM, ADC, SoftI2C
import utils
import sys


class Devices:
    def __init__(self):
        self.lcd = None
        self.lcd_light = True
        self.servo = None
        self.servo_pin = None
        self.display = None
        self.adc = None
        self.button = None
        self.thermometer = None

        if int(utils.get_config("servo_pin", -1)) > -1:
            self.servo_pin = Pin(int(utils.get_config("servo_pin", 4)))
            self.servo = PWM(self.servo_pin, freq=50)
            self.servo.duty(20)
            self.servo.duty(utils.map_temp_to_servo(int(utils.get_config("piec_temperatura", 40))))
            del self.servo

        if int(utils.get_config("lcd_sda_pin", -1)) > -1:
            from esp8266_i2c_lcd import I2cLcd
            self.i2c = SoftI2C(scl=Pin(int(utils.get_config("lcd_scl_pin", -1))),
                               sda=Pin(int(utils.get_config("lcd_sda_pin", -1))),
                               freq=100000)
            self.lcd = I2cLcd(self.i2c, 0x27, 2, 16)
            self.lcd_wifi_chars(self.lcd)

            self.lcd.hide_cursor()
            self.lcd.clear()

        if int(utils.get_config("button_pin", -1)) > -1:
            self.button = Pin(int(utils.get_config("button_pin", 5)), Pin.IN, Pin.PULL_UP)
        if int(utils.get_config("adc_pin", -1)) > -1:
            if sys.platform == "esp8266":
                self.adc = ADC(int(utils.get_config("adc_pin", 0)))
            elif sys.platform == "esp32":
                self.adc = ADC(Pin(int(utils.get_config("adc_pin", 2))))
                self.adc.atten(ADC.ATTN_11DB)
                self.adc.width(ADC.WIDTH_10BIT)

        if int(utils.get_config("thermometer_pin", -1)) > -1:
            import sensors
            self.thermometer = sensors.Sensory()

    def lcd_wifi_chars(self, lcd):
        if lcd is None:
            return
        lcd.custom_char(0, bytearray([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10]))
        lcd.custom_char(1, bytearray([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x08, 0x18]))
        lcd.custom_char(2, bytearray([0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x0C, 0x1C]))
        lcd.custom_char(3, bytearray([0x00, 0x00, 0x00, 0x00, 0x02, 0x06, 0x0E, 0x1E]))
        lcd.custom_char(4, bytearray([0x00, 0x00, 0x00, 0x01, 0x03, 0x07, 0x0F, 0x1F]))
        lcd.custom_char(7, bytearray([0x06, 0x09, 0x09, 0x06, 0x00, 0x00, 0x00, 0x00]))

    def write_display(self, fld, val):
        if self.display is not None:
            self.display._write(fld, val)

    async def move_servo(self, val):
        if self.servo_pin is not None:
            self.servo = PWM(self.servo_pin, freq=50)
            self.servo.duty(val)
            del self.servo

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

    def write_lcd_char_at_pos(self, char, x, y):
        if self.lcd is not None:
            self.lcd.move_to(x, y)
            self.lcd.putchar(char)

    def lcd_backlight(self, val):
        if self.lcd is not None:
            self.lcd_light = val
            if val == 0:
                self.lcd.hal_backlight_on()
            else:
                self.lcd.hal_backlight_off()

    def lcd_light_tick(self):
        self.lcd_light += 1
        if self.lcd_light > 120 * int(utils.get_config("lcd_backlight", 2)):
            self.lcd_backlight(-1)
