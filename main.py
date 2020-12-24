from machine import Pin, SPI, PWM, ADC
import utils
import utime
import usocket as socket
import gc
import select
import max7219
import sensors


class piec:
    def __init__(self):
        self.servo_pin = Pin(int(utils.get_config("servo_pin", 4)))
        self.servo = PWM(self.servo_pin, freq=50)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.lh = 0
        self.lm = 0
        self.time_update = 0

        self.spi = SPI(1, baudrate=10000000, polarity=0, phase=0)
        self.display_pin = Pin(int(utils.get_config("wyswietlacz_pin", 15)), Pin.OUT)
        self.display = max7219.Matrix8x8(self.spi, self.display_pin, 1)
        self.display.brightness(0)
        self.display.fill(0)
        self.display.show()

        self.button = Pin(utils.get_config("przycisk_pin", 5), Pin.IN, Pin.PULL_UP)
        self.btn_val = 1

        self.joy_val = 500
        self.edit_temp = 0

        self.state = 1  # 0-sleep, 1 - display, 2 - edit
        self.edit_state = 0
        self.adc = ADC(0)

        self.termometr = sensors.sensory()

        utils.wifi_disconnect()

    def led_write_number(self, val, move=0, dots=[]):
        digits = {1: 48, 2: 109, 3: 121, 4: 51, 5: 91, 6: 95, 7: 112, 8: 127, 9: 123, 0: 126}
        values = []
        print(val)
        print(values)
        while val > 0:
            d = int(val % 10)
            print("d",d)
            val = int(val / 10)
            print("val",val)
            v = digits[d]
            values.append(v)
            print("values",values)
        values.reverse()
        pos = 8 - move
        print(values)
        i = len(values)
        for d in values:
            print('pos',pos)
            if dots.count(i) > 0:
                d += 128

            self.display._write(pos, d)
            pos -= 1
            i -= 1

    def parse_temp_to_servo(self, temp):
        min_servo = int(utils.get_config("servo_min", 37))
        max_servo = int(utils.get_config("servo_max", 115))
        servo_pos = utils.val_map(temp, 30, 90, min_servo, max_servo)
        return servo_pos

    def set_temperature(self, new_temp):
        y = utime.localtime(utime.time() + 1 * 3600)[0]
        m = utime.localtime(utime.time() + 1 * 3600)[1]
        d = utime.localtime(utime.time() + 1 * 3600)[2]
        h = utime.localtime(utime.time() + 1 * 3600)[3]
        mm = utime.localtime(utime.time() + 1 * 3600)[4]
        czas = "%s-%s-%s %s:%s" % (str(y), str(m), str(d), str(h), str(mm))
        utils.set_config("piec_ostatnia_aktualizacja", czas)
        curr_temp = int(utils.get_config("piec_temperatura"))

        if curr_temp < new_temp <= (int(utils.get_config("piec_temperatura_max", 90)) - 5):
            set_temp = new_temp + 5
            self.servo.duty(self.parse_temp_to_servo(set_temp))
            utime.sleep_ms(1000)

        self.servo.duty(self.parse_temp_to_servo(new_temp))
        utils.set_config("piec_temperatura", int(new_temp))
        utime.sleep_ms(150)

        if self.state > 0:
            self.led_write_number(new_temp)

    def save_times(self, times):
        tms = {}
        times = times.replace("%3A", ":")
        times = times.replace("+-+", " - ")
        times = times.replace("%0D%0A", "\n")
        for r in times.split('\n'):
            if r != '':
                key = r.split(' - ')[0]
                val = r.split(' - ')[1]
                tms[key] = int(val)
        utils.set_config("piec_czasy", tms)

    def web_save(self, temp, times):
        tmp = int(temp)
        curr_tmp = int(utils.get_config("piec_temperatura", tmp))
        if tmp != curr_tmp:
            self.set_temperature(int(tmp))
        self.save_times(times)

    def web_template(self):
        temp = utils.get_config("piec_temperatura")
        times = utils.get_config("piec_czasy", {})
        last = utils.get_config("piec_ostatnia_aktualizacja", '')
        temperatura = self.termometr.pomiar_temperatury()
        tm = ''
        y = utime.localtime(utime.time() + 1 * 3600)[0]
        m = utime.localtime(utime.time() + 1 * 3600)[1]
        d = utime.localtime(utime.time() + 1 * 3600)[2]
        h = utime.localtime(utime.time() + 1 * 3600)[3]
        mm = utime.localtime(utime.time() + 1 * 3600)[4]
        for t in times:
            tm += t + ' - ' + str(times[t]) + '\n'
        html = """<!DOCTYPE html>
<head>
    <meta charset='UTF-8'>
</head>
<title>Kontrola pieca</title>
<body>
  <h3>Kontrola pieca</h3>
  <p>Czas na urządzeniu: %s-%s-%s %s:%s</p>
  <p>Pomiar temperatury: %s</p>
  <p>Ostatnia zmiana temperatury: %s</p>
  <form action="/save" method="get">
      <p>Temperatura ustawiona:<br><input type="number" name="temp" max="90" min="30" value="%s"></p>
      <input type="hidden" name="tempEnd">
      <p>Harmonogram<br> format hh:mm - temperatura (np: 22:00 - 40):<br>
      <textarea rows="10" name="times">%s</textarea>
      </p>
      <input type="hidden" name="timesEnd">
      <button type="submit">ZAPISZ</button>
  </form>
</body>
</html>
""" % (str(y), str(m), str(d), str(h), str(mm), str(temperatura), last, str(temp), tm)
        return html

    def handle_timer(self):
        times = utils.get_config("piec_czasy", {})
        if self.time_update == 0:
            utils.settime()
            self.time_update = 1

        h = utime.localtime(utime.time() + 1 * 3600)[3]
        mm = utime.localtime(utime.time() + 1 * 3600)[4]
        if self.lh == h and self.lm == mm:
            return
        self.lh = h
        self.lm = mm

        for t in times:
            th = t.split(':')[0]
            tm = int(t.split(':')[1])
            if (th == '*' or int(th) == h) and tm == mm:
                tmp = times[t]
                self.set_temperature(int(tmp))

    def handle_web(self, conn, addr):
        conn.settimeout(0.5)
        request = conn.recv(2048)

        conn.settimeout(None)
        request = str(request)
        save = request.find("/save""")
        if save > -1:
            start = request.find("temp=") + len("temp=")
            end = request.find("&tempEnd")
            temp = int(request[start:end])
            start = request.find("times=") + len("times=")
            end = request.find("&timesEnd")
            times = request[start:end]
            self.web_save(temp, times)

        response = self.web_template()
        conn.send('HTTP/1.1 200 OK\n')
        conn.send('Content-Type: text/html\n')
        conn.send('Connection: close\n\n')
        conn.sendall(response)
        utime.sleep(1)
        conn.close()

    def handle_joystick(self):
        if self.edit_temp == 0:
            self.edit_temp = int(utils.get_config("piec_temperatura", 0))
        if self.state in (2, 3, 4, 5):
            val = self.adc.read()
            if val <= 200:
                if self.edit_temp < int(utils.get_config("piec_temperatura_max", 90)):
                    self.edit_temp += 1
                    self.led_write_number(self.edit_temp)
                utime.sleep_ms(150)
            if val >= 900:
                if self.edit_temp > int(utils.get_config("piec_temperatura_min", 30)):
                    self.edit_temp -= 1
                    self.led_write_number(self.edit_temp)
                utime.sleep_ms(150)
            self.joy_val = val

    def handle_button(self, pin):
        if self.btn_val == 1 and pin.value() == 0:
            self.state += 1
            if self.state == 1:
                curr_temp = int(utils.get_config("piec_temperatura", 0))
                self.led_write_number(curr_temp)
            if self.state == 2:
                self.edit_temp = int(utils.get_config("piec_temperatura", 0))
            if self.state == 3:
                self.state = 1
                curr_temp = int(utils.get_config("piec_temperatura", 0))
                if self.edit_temp != curr_temp:
                    self.set_temperature(int(self.edit_temp))
                    self.led_write_number(self.edit_temp)
                self.edit_temp = 0
                self.display._write(5, 0)
        self.btn_val = pin.value()

    def init(self):
        if utils.wifi_connected() is False:
            utils.load_config()
            self.set_temperature(int(utils.get_config("piec_temperatura", 40)))
            utils.wifi_connect()

            if utils.wifi_connected() is True:
                try:
                    self.sock.bind(('', 80))
                    self.sock.listen(5)
                except OSError as err:
                    pass

    def run(self):
        while True:
            if self.state < 2:
                self.init()
                if utils.wifi_connected():
                    r, w, err = select.select((self.sock,), (), (), 1)
                    if r:
                        for readable in r:
                            try:
                                conn, addr = self.sock.accept()
                                self.handle_web(conn, addr)
                            except OSError as e:
                                conn.close()
                self.handle_timer()

                t = self.termometr.pomiar_temperatury()
                self.led_write_number(int(round(t*10)), 5, [2])

            else:
                if self.edit_state % 2 == 0:
                    self.display._write(5, 79)
                else:
                    self.display._write(5, 0)
                self.edit_state += 1
                if self.edit_state > 100:
                    self.edit_state = 0



            self.handle_joystick()
            self.handle_button(self.button)


utils.load_config()
p = piec()
p.run()
