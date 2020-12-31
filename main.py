from machine import Pin, SPI, PWM, ADC
import utils
import utime
import usocket as socket
import select
import max7219
import sensors
import webtemplate
import gc

class Piec:
    def __init__(self):
        self.servo_pin = Pin(int(utils.get_config("servo_pin", 4)))
        self.servo = PWM(self.servo_pin, freq=50)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        utils.log_message('INIT 1')
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

            self.display._write(pos, d)
            pos -= 1
            i -= 1

    def set_temperature(self, new_temp, zapisz=True):
        czas = utils.czas()
        if zapisz is True:
            utils.set_config("piec_ostatnia_aktualizacja", czas)
        curr_temp = int(utils.get_config("piec_temperatura"))

        if curr_temp < new_temp <= (int(utils.get_config("piec_temperatura_max", 90)) - 5):
            set_temp = new_temp + 5
            self.servo.duty(utils.map_temp_to_servo(set_temp))
            utime.sleep_ms(1000)

        utils.log_message('SET TEMPERATURE: %s' % (str(new_temp)))
        self.servo.duty(utils.map_temp_to_servo(new_temp))
        utils.set_config("piec_temperatura", int(new_temp))
        if zapisz is True:
            historia = utils.get_config("piec_temperatura_historia", {})
            historia[czas] = new_temp
            utils.set_config("piec_temperatura_historia", historia)

        utime.sleep_ms(150)

        if self.state > 0:
            self.led_write_number(new_temp)

    def save_times(self, times):
        tms = {}
        times = times.replace("%3A", ":").replace("+-+", " - ").replace("%0D%0A", "\n")
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



    def handle_timer(self):
        times = utils.get_config("piec_czasy", {})
        if self.time_update == 0 and utils.wifi_connected():
            utils.settime()
            self.time_update = 1

        hh = utime.localtime(utime.time() + 1 * 3600)[3]
        mm = utime.localtime(utime.time() + 1 * 3600)[4]
        ss = utime.localtime(utime.time() + 1 * 3600)[5]
        if self.lh == hh and self.lm == mm:
            return
        self.lh = hh
        self.lm = mm

        for t in times:
            th = t.split(':')[0]
            tm = int(t.split(':')[1])
            if (th == '*' or int(th) == hh) and tm == mm:
                tmp = times[t]
                utils.log_message('HANDLE TIME %2d:%2d - %2d' % (th, tm, tmp))
                self.set_temperature(int(tmp))

        if mm % 10 == 0 and utils.wifi_connected():
            utils.log_message('SET TIME')
            utils.settime()

    def handle_web(self, conn, addr):
        conn.settimeout(0.5)
        gc.collect()
        request = b''
        while True:

            try:
                buf = b''
                buf = conn.recv(128)
            except Exception as erar:
                pass
            request += buf

            if buf == b'':
                break
        conn.settimeout(None)
        request = str(request)
        utils.log_message('WEB REQUEST')
        save = request.find("/save""")
        if save > -1:
            start = request.find("temp=") + len("temp=")
            end = request.find("&tempEnd")
            temp = int(request[start:end])
            start = request.find("times=") + len("times=")
            end = request.find("&timesEnd")
            times = request[start:end]
            self.web_save(temp, times)

        if request.find("/logs""") > -1:
            conn.send('HTTP/1.1 200 OK\n')
            conn.send('Content-Type: text/plain\n')
            conn.send('Connection: close\n\n')
            log_file = open('log.txt', 'r')
            while True:
                buf = log_file.read(128)
                if buf == '':
                    break
                else:
                    conn.send(buf)
            log_file.close()
        elif request.find("/config""") > -1:
            conn.send('HTTP/1.1 200 OK\n')
            conn.send('Content-Type: text/plain\n')
            conn.send('Connection: close\n\n')
            conn.sendall(utils.config)
        else:
            temper = self.termometr.pomiar_temperatury()
            response = webtemplate.get_template(temper)
            conn.send('HTTP/1.1 200 OK\n')
            conn.send('Content-Type: text/html\n')
            conn.send('Connection: close\n\n')
            conn.sendall(response)

        utime.sleep(50)
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

    def init_wifi(self):
        if utils.wifi_connected() is False:
            utils.wifi_connect()
            if utils.wifi_connected() is True:
                try:
                    self.sock.bind(('', 80))
                    self.sock.listen(5)
                except OSError as err:
                    pass
                    utils.log_message('WIFI ERROR')
                    utils.log_message(repr(err))

    def run(self):
        wifid = 0
        while True:
            if self.state < 2:
                self.init_wifi()
                if utils.wifi_connected():
                    r, w, err = select.select((self.sock,), (), (), 5)
                    if r:
                        for readable in r:
                            try:
                                conn, addr = self.sock.accept()
                                self.handle_web(conn, addr)
                            except OSError as error:
                                utils.log_message('WEB ERROR')
                                utils.log_message(repr(error))
                                conn.close()
                else:
                    wifid += 1
                    utils.log_message('WIFI DOWN')
                    if wifid > 10:
                        utils.log_message('WIFI RECONNECT')
                        utils.wifi_disconnect()
                        wifid = 0

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
            utils.log_message('FREE MEMORY: %s' % (str(gc.mem_free())))
            gc.collect()


utils.log_message('START')
utils.load_config()
utils.wifi_disconnect()
while True:
    try:
        p = Piec()
        p.set_temperature(int(utils.get_config("piec_temperatura", 40)), False)
        utils.log_message('RUN')
        p.run()
    except Exception as err:
        utils.log_message('GENERAL EXCEPTION')
        utils.log_message(repr(err))

    gc.collect()
    utils.log_message('CRASH!')
