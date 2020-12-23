from machine import Pin, SPI, PWM, ADC
import utils
import utime
import usocket as socket
import gc
import select
import max7219


class piec:
    def __init__(self):
        self.servo_pin = Pin(4)
        self.servo = PWM(self.servo_pin, freq=50,)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.lh = 0
        self.lm = 0
        self.time_update = 0

        self.spi = SPI(1, baudrate=10000000, polarity=0, phase=0)
        self.display_pin = Pin(15, Pin.OUT)
        self.display = max7219.Matrix8x8(self.spi, self.display_pin, 1)
        self.display.brightness(0)
        self.display.fill(0)
        self.display.show()

        self.button = Pin(5, Pin.IN, Pin.PULL_UP)
        self.btn_val = 1

        self.joy_val = 500
        self.edit_temp = 0

        self.state = 1  # 0-sleep, 1 - display, 2 - edit
        self.edit_state = 0
        self.adc = ADC(0)

        utils.wifi_disconnect()

    def led_write_number(self, val, where=1, dots=False):
        d1 = int(val / 10)
        d2 = int(val % 10)
        digits = {1: 48, 2: 109, 3: 121, 4: 51, 5: 91, 6: 95, 7: 112, 8: 127, 9: 123, 0: 126}
        v1 = digits[d1]
        v2 = digits[d2]

        if where == 1:
            dp1 = 8
            dp2 = 7
        else:
            dp1 = 2
            dp2 = 1

        if dots is True:
            v1 += 128
            v2 += 128

        self.display._write(dp1, v1)  # 1
        self.display._write(dp2, v2)  # 2

    def parse_temp_to_servo(self, temp):
        min_servo = int(utils.get_config("servo_min", "30"))
        max_servo = int(utils.get_config("servo_max", "115"))
        servo_pos = utils.val_map(temp, 10, 90, min_servo, max_servo)
        return servo_pos

    def set_temperature(self, temp):
        y = utime.localtime(utime.time() + 1 * 3600)[0]
        m = utime.localtime(utime.time() + 1 * 3600)[1]
        d = utime.localtime(utime.time() + 1 * 3600)[2]
        h = utime.localtime(utime.time() + 1 * 3600)[3]
        mm = utime.localtime(utime.time() + 1 * 3600)[4]
        czas = "%s-%s-%s %s:%s" % (str(y), str(m), str(d), str(h), str(mm))
        utils.set_config("last_temp_update", czas)
        print('temp:', temp)
        self.servo.duty(self.parse_temp_to_servo(temp))
        utime.sleep_ms(150)
        if self.state > 0:
          self.led_write_number(temp, 1, False)

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
        print('times to save:', tms)
        utils.set_config("piec_times", tms)

    def web_save(self, temp, times):
        tmp = int(temp)
        curr_tmp = int(utils.get_config('piec_temperature', tmp))
        if tmp != curr_tmp:
            utils.set_config('piec_temperature', tmp, False)
            print('set 1')
            self.set_temperature(int(tmp))
        self.save_times(times)

    def web_template(self):
        temp = utils.get_config('piec_temperature')
        times = utils.get_config("piec_times", {})
        last = utils.get_config('last_temp_update', '')
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
  <p>Ostatnia zmiana temperatury: %s</p>
  <form action="/save" method="get">
      <p>Temperatura:<br><input type="number" name="temp" max="90" min="10" value="%s"></p>
      <input type="hidden" name="tempEnd">
      <p>Harmonogram<br> format hh:mm - temperatura (np: 22:00 - 40):<br>
      <textarea rows="10" name="times">%s</textarea>
      </p>
      <input type="hidden" name="timesEnd">
      <button type="submit">ZAPISZ</button>
  </form>
</body>
</html>
""" % (str(y), str(m), str(d), str(h), str(mm), last, str(temp), tm)
        return html

    def handle_timer(self):
        times = utils.get_config("piec_times", "")
        if self.time_update == 0:
            utils.settime()
            self.time_update = 1

        h = utime.localtime(utime.time() + 1 * 3600)[3]
        mm = utime.localtime(utime.time() + 1 * 3600)[4]
        # print("Handle timer", lh, lm, h, mm)
        if self.lh == h and self.lm == mm:
            return
        self.lh = h
        self.lm = mm

        for t in times:
            th = t.split(':')[0]
            tm = int(t.split(':')[1])
            # print("Time: ", h, mm, th, tm)
            if (th == '*' or int(th) == h) and tm == mm:
                # print(th, tm, h, mm)
                tmp = times[t]
                # print("Time handled")
                utils.set_config('piec_temperature', int(tmp))
                # print('set 2')
                self.set_temperature(int(tmp))

    def handle_web(self, conn, addr):
        conn.settimeout(0.5)
        print('Got a connection from %s' % str(addr))
        request = conn.recv(2048)

        conn.settimeout(None)
        request = str(request)
        print('Content = %s' % request)
        save = request.find('/save')
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
        print("resp:", response)

    def handle_joystick(self):
        if self.edit_temp == 0:
            self.edit_temp = int(utils.get_config('piec_temperature', '0'))
        if self.state in (2, 3, 4, 5):
            val = self.adc.read()
            if val >= 900:
                self.edit_temp += 1
                print('joy up', self.joy_val, val)
                self.led_write_number(self.edit_temp, 1, False)
                utime.sleep_ms(150)
            if  val <= 200:
                self.edit_temp -= 1
                print('joy down', self.joy_val, val)
                self.led_write_number(self.edit_temp, 1, False)
                utime.sleep_ms(150)
            self.joy_val = val

    def handle_button(self, pin):
        if self.btn_val == 1 and pin.value() == 0:
            self.state += 1
            if self.state == 1:
                curr_temp = int(utils.get_config('piec_temperature', '0'))
                self.led_write_number(curr_temp, 1, False)
            if self.state == 2:
                self.edit_temp = int(utils.get_config('piec_temperature', '0'))
            if self.state == 3:
                self.state = 1
                print('SET TEMP 1', self.edit_temp)
                curr_temp = int(utils.get_config('piec_temperature', '0'))
                if self.edit_temp != curr_temp:
                    print('SAVE TEMP!')
                    utils.set_config('piec_temperature', int(self.edit_temp))
                    self.set_temperature(int(self.edit_temp))
                    self.led_write_number(curr_temp, 1, False)
                self.edit_temp = 0
        self.btn_val = pin.value()

    def init(self):
        if utils.wifi_connected() is False:
            print("Load config")
            utils.load_config()
            print("set temp")
            self.set_temperature(int(utils.get_config("piec_temperature", 40)))

            print("wifi connect")
            utils.wifi_connect()
            print("Web start")

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


p = piec()
p.run()
