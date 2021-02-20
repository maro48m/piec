import utils
import json
import sensors
from web_helper import get_header


async def send_file(writer, file_name, header):
    writer.write(get_header(header).encode('utf8'))
    try:
        buf = None

        await utils.lock_file(file_name)

        with open(file_name, 'r') as fi:
            while True:
                buf = fi.read(4096)
                if str(buf) == '':
                    break
                else:
                    writer.write(buf.encode('utf8'))
                    await writer.drain()
                del buf
            fi.close()

    except Exception as eee:
        # utils.log_message('BLAD ODCZYTU PLIKU %s' % file_name, 2)
        utils.log_exception(eee, 2)

    utils.unlock_file(file_name)
    if buf is not None:
        del buf
    return True


async def handle_api(writer, request):
    if request["url"].find("/api/dane.json") > -1:

        termometr = sensors.Sensory()
        dane = utils.get_data()
        dane["termometr"] = await termometr.pomiar_temperatury()
        del termometr

        writer.write(get_header('application/json'))
        writer.write(json.dumps(dane).encode('utf-8'))
        await writer.drain()
    elif request["url"].find("/api/clear/logs") > -1:
        utils.remove_hist(4)
        writer.write(get_header('application/json'))
        writer.write('{"response":"OK"}'.encode('utf-8'))
        await writer.drain()
    elif request["url"].find("/api/clear/hist_piec") > -1:
        utils.remove_hist(1)
        writer.write(get_header('application/json'))
        writer.write('{"response":"OK"}'.encode('utf-8'))
        await writer.drain()
    elif request["url"].find("/api/clear/hist_termo") > -1:
        utils.remove_hist(2)
        writer.write(get_header('application/json'))
        writer.write('{"response":"OK"}'.encode('utf-8'))
        await writer.drain()
    elif request["url"].find("/api/clear/all") > -1:
        utils.remove_hist(7)
        writer.write(get_header('application/json'))
        writer.write('{"response":"OK"}'.encode('utf-8'))
        await writer.drain()
    elif request["url"].find("/api/config.json") > -1:
        writer.write(get_header('application/json'))
        writer.write(json.dumps(utils.config).encode('utf-8'))
        await writer.drain()
    elif request["url"].find("/api/params_save") > -1:
        utils.update_config(request["body"].decode('utf-8'))
        writer.write(get_header('application/json'))
        writer.write('{"response":"OK"}'.encode('utf-8'))
        await writer.drain()
    elif request["url"].find("/api/logs") > -1:
        await send_file(writer, 'log.txt', 'text/plain')
    elif request["url"].find("/api/hist_piec") > -1:
        await send_file(writer, 'piec.hist', 'text/plain')
    elif request["url"].find("/api/hist_termo") > -1:
        await send_file(writer, 'termometr.hist', 'text/plain')
    elif request["url"].find("/api/chart.json") > -1:
        writer.write(get_header('application/json'))
        await send_chart_data2(writer)
    elif request["url"].find("/api/file") > -1:
        writer.write(get_header('application/json'))
        if upload_file(request):
            writer.write('{"response":"Aktualizacja pomyślna"}'.encode('utf-8'))
        else:
            writer.write('{"response":"Błąd aktualizacji"}'.encode('utf-8'))
        await writer.drain()
    return True


async def send_chart_data(writer):
    for i in range(1, 3):
        if i == 1:
            file_name = 'termometr.hist'
            data = """[{"name": "Termometr", "data": ["""
            termometr = sensors.Sensory()
            curr = await termometr.pomiar_temperatury()
            del termometr
            sqr = False
        else:
            file_name = 'piec.hist'
            data = """{"name": "Piec", "data": ["""
            curr = int(utils.get_config("piec_temperatura", 40))
            sqr = True
        prev = None
        writer.write(data.encode('utf-8'))
        await writer.drain()

        try:
            await utils.lock_file(file_name)

            with open(file_name, 'r') as fi:
                while True:
                    buf = fi.readline()
                    if str(buf) == '':
                        break
                    else:
                        d = buf.rstrip().split(" - ")

                        if sqr and prev is not None:
                            dp = buf.rstrip().split(" - ")
                            dp[1] = prev
                            dp[0] += " GMT"
                            writer.write((json.dumps(dp)+',').encode('utf-8'))
                            await writer.drain()

                        prev = d[1]
                        d[0] += " GMT"
                        writer.write((json.dumps(d)+',').encode('utf-8'))
                        await writer.drain()
                fi.close()
        except Exception as eee:
            #utils.log_message('BLAD ODCZYTU PLIKU %s' % file_name, 2)
            utils.log_exception(eee, 2)
            pass

        if sqr:
            d = [utils.czas(True)+' GMT', prev]
            writer.write((json.dumps(d)+',').encode('utf-8'))
            await writer.drain()

        d = [utils.czas(True)+' GMT', curr]
        writer.write(json.dumps(d).encode('utf-8'))
        await writer.drain()

        if i == 1:
            writer.write("""]},""".encode('utf-8'))
        else:
            writer.write("""]}]""".encode('utf-8'))

        await writer.drain()
        utils.unlock_file(file_name)


async def send_chart_data2(writer):
    for i in range(1, 3):
        if i == 1:
            file_name = 'termometr.hist'
            data = """[{"name": "Termometr", "data": ["""
            termometr = sensors.Sensory()
            curr = await termometr.pomiar_temperatury()
            del termometr
            sqr = False
        else:
            file_name = 'piec.hist'
            data = """{"name": "Piec", "data": ["""
            curr = int(utils.get_config("piec_temperatura", 40))
            sqr = True
        prev = None
        writer.write(data.encode('utf-8'))
        await writer.drain()

        try:
            await utils.lock_file(file_name)

            with open(file_name, 'r') as fi:
                c = 0
                data = ""
                while True:
                    buf = fi.readline()
                    if str(buf) == '':
                        break
                    else:
                        d = buf.rstrip().split(" - ")

                        if sqr and prev is not None:
                            dp = buf.rstrip().split(" - ")
                            dp[1] = prev
                            dp[0] += " GMT"
                            data += (json.dumps(dp)+',')

                        prev = d[1]
                        d[0] += " GMT"
                        data += (json.dumps(d)+',')
                        c += 1
                        if c == 240:
                            writer.write(data.encode('utf-8'))
                            await writer.drain()
                            c = 0
                            data = ""

                fi.close()
        except Exception as eee:
            #utils.log_message('BLAD ODCZYTU PLIKU %s' % file_name, 2)
            utils.log_exception(eee, 2)
            pass

        if sqr:
            d = [utils.czas(True)+' GMT', prev]
            data += (json.dumps(d)+',')

        d = [utils.czas(True)+' GMT', curr]
        data += (json.dumps(d))

        writer.write(data.encode('utf-8'))
        await writer.drain()

        if i == 1:
            writer.write("""]},""".encode('utf-8'))
        else:
            writer.write("""]}]""".encode('utf-8'))

        await writer.drain()
        utils.unlock_file(file_name)


def upload_file(request):
    #Content-Type': 'multipart/form-data; boundary=----WebKitFormBoundaryUdPTIt4xUUzNAXmx
    # ------WebKitFormBoundaryUdPTIt4xUUzNAXmx
    # Content-Disposition: form-data; name="start"
    #
    # 640
    # ------WebKitFormBoundaryUdPTIt4xUUzNAXmx
    # Content-Disposition: form-data; name="end"
    #
    # 768
    # ------WebKitFormBoundaryUdPTIt4xUUzNAXmx
    # Content-Disposition: form-data; name="chunks"
    #
    # 86
    # ------WebKitFormBoundaryUdPTIt4xUUzNAXmx
    # Content-Disposition: form-data; name="chunk"
    #
    # 6
    # ------WebKitFormBoundaryUdPTIt4xUUzNAXmx
    # Content-Disposition: form-data; name="file_name"
    #
    # main.py
    # ------WebKitFormBoundaryUdPTIt4xUUzNAXmx
    # Content-Disposition: form-data; name="file"; filename="blob"
    # Content-Type: application/octet-stream
    #
    # utils.get_config("piec_historia_temperatury", True) is True:\r\n            if utime.localtime(utime.time() + 1 * 3600)[0] > 2000:
    # ------WebKitFormBoundaryUdPTIt4xUUzNAXmx--

    return True
