import machine
import onewire
import ds18x20
import utime
import utils
import dht


class sensory:
    def __init__(self):
        utils.load_config()
        self.termo_pin = int(utils.get_config('termometr_pin'))
        self.termo_res = int(utils.get_config('termometr_rozdzielczosc'))
        self.termo_cnt = int(utils.get_config('termometr_powtorzen'))

    def pomiar_temperatury(self):
        temperatura = 0
        cnt = 0
        dat = machine.Pin(self.termo_pin)
        ds = ds18x20.DS18X20(onewire.OneWire(dat))
        roms = ds.scan()
        config = b'\x00\x00\x1f'

        for rom in roms:
            # bajty 2 3 i 4 konfiguracji
            # 2 i 3 - dane uzytkownika
            # 4 - rozdzielczosc
            if self.termo_res == 9:
                config = b'\x00\x00\x1f'
            if self.termo_res == 10:
                config = b'\x00\x00\x3f'
            if self.termo_res == 11:
                config = b'\x00\x00\x5f'
            if self.termo_res == 12:
                config = b'\x00\x00\x7f'

            ds.write_scratch(rom, config)
            cnt += 1
        for x in range(self.termo_cnt):
            ds.convert_temp()

            utime.sleep_ms(int(750 / (2 ** (12 - self.termo_res))))
            for rom in roms:
                t = ds.read_temp(rom)
                temperatura += t

            # tmp = tmp / (i * 1.0)
            # temperatura += tmp
            # tmp = 0

        temperatura = temperatura / (self.termo_cnt * cnt * 1.0)
        return temperatura
