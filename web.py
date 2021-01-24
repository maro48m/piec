import utils
import json
import sensors
import utime

def send_file(socket, file_name, header):
    socket.sendall(get_header(header))
    try:
        while utils.file_locked(file_name):
            utime.sleep_ms(1)

        utils.lock_file(file_name)

        with open(file_name, 'r') as fi:
            while True:
                buf = fi.read(128)
                if str(buf) == '':
                    break
                else:
                    if socket is not None:
                        socket.sendall(buf)
            fi.close()
    except Exception as eee:
        utils.log_message('WWW FILE ERROR %s' % file_name)
        utils.log_exception(eee)

    utils.wait_for_file()
    utils.unlock_file(file_name)
    del buf
    return True


def get_header(mime_type):
    return "HTTP/1.1 200OK\n" + "Content-Type: %s\n" % mime_type + "Connection: close\n\n"


def handle_api(socket, request):
    if request["url"].find("/api/dane.json") > -1:

        termometr = sensors.Sensory()
        dane = utils.get_data()
        dane["termometr"] = termometr.pomiar_temperatury()
        del termometr

        socket.sendall(get_header('application/json'))
        socket.sendall(json.dumps(dane))
    elif request["url"].find("/api/clear/logs") > -1:
        socket.sendall(get_header('text/plain'))
        utils.remove_hist(4)
        socket.sendall('OK')
    elif request["url"].find("/api/clear/hist_piec") > -1:
        socket.sendall(get_header('text/plain'))
        utils.remove_hist(1)
        socket.sendall('OK')
    elif request["url"].find("/api/clear/hist_termo") > -1:
        socket.sendall(get_header('text/plain'))
        utils.remove_hist(2)
        socket.sendall('OK')
    elif request["url"].find("/api/clear/all") > -1:
        socket.sendall(get_header('text/plain'))
        utils.remove_hist(7)
        socket.sendall('OK')
    elif request["url"].find("/api/config.json") > -1:
        socket.sendall(get_header('application/json'))
        socket.sendall(json.dumps(utils.config))
    elif request["url"].find("/api/params_save") > -1:
        utils.update_config(request["body"].decode('utf-8'))
        socket.sendall(get_header('application/json'))
        socket.sendall('OK')
    elif request["url"].find("/api/logs") > -1:
        send_file(socket, 'log.txt', 'text/plain')
    elif request["url"].find("/api/hist_piec") > -1:
        send_file(socket, 'piec.hist', 'text/plain')
    elif request["url"].find("/api/hist_termo") > -1:
        send_file(socket, 'termometr.hist', 'text/plain')
    elif request["url"].find("/api/chart.json") > -1:
        socket.sendall(get_header('application/json'))
        send_chart_data(socket)
    elif request["url"].find("/api/file") > -1:
        socket.sendall(get_header('text/plain'))
        if upload_file(request):
            socket.sendall('Aktualizacja pomyślna')
        else:
            socket.sendall('Błąd aktualizacji')
    return True


def send_chart_data(socket):
    for i in range(1, 3):
        if i == 1:
            file_name = 'termometr.hist'
            data = """[{"name": "Termometr", "data": ["""
            termometr = sensors.Sensory()
            curr = termometr.pomiar_temperatury()
            del termometr
            sqr = False
        else:
            file_name = 'piec.hist'
            data = """{"name": "Piec", "data": ["""
            curr = int(utils.get_config("piec_temperatura", 40))
            sqr = True
        prev = None
        socket.sendall(data)
        try:
            while utils.file_locked(file_name):
                utime.sleep_ms(1)

            utils.lock_file(file_name)

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
                            socket.sendall(json.dumps(dp)+',')

                        prev = d[1]
                        d[0] += " GMT"
                        socket.sendall(json.dumps(d)+',')
                fi.close()
        except Exception as eee:
            utils.log_message('BLAD ODCZYTU PLIKU %s' % file_name)
            utils.log_exception(eee)

        if sqr:
            d = [utils.czas(True)+' GMT', prev]
            socket.sendall(json.dumps(d)+",")

        d = [utils.czas(True)+' GMT', curr]
        socket.sendall(json.dumps(d))

        if i == 1:
            socket.sendall("""]},""")
        else:
            socket.sendall("""]}]""")

        utils.wait_for_file()
        utils.unlock_file(file_name)

# r1 = b'POST /api/file HTTP/1.1\r\nHost: 192.168.0.136\r\nConnection: keep-alive\r\nContent-Length: 693\r\nUser-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Safari/537.36 OPR/73.0.3856.344\r\nContent-Type: multipart/form-data; boundary=----WebKitFormBoundaryyWZOmCEmrqIYb3Zj\r\nAccept: */*\r\nOrigin: http://192.168.0.136\r\nReferer: http://192.168.0.136/fileup\r\nAccept-Encoding: gzip, deflate\r\nAccept-Language: pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7\r\n\r\n------WebKitFormBoundaryyWZOmCEmrqIYb3Zj\r\nContent-Disposition: form-data; name="start"\r\n\r\n0\r\n------WebKitFormBoundaryyWZOmCEmrqIYb3Zj\r\nContent-Disposition: form-data; name="end"\r\n\r\n128\r\n------WebKitFormBoundaryyWZOmCEmrqIYb3Zj\r\nContent-Disposition: form-data; name="chunks"\r\n\r\n2\r\n------WebKitFormBoundaryyWZOmCEmrqIYb3Zj\r\nContent-Disposition: form-data; name="chunk"\r\n\r\n1\r\n------WebKitFormBoundaryyWZOmCEmrqIYb3Zj\r\nContent-Disposition: form-data; name="file"; filename="blob"\r\nContent-Type: application/octet-stream\r\n\r\n192.168.1.1\r\nw grupe \xb3\xb9czno\x9\xe6 guzik trybika\r\nzalogowa\xe6 si\xea (admin/admin)\r\nnajecha\xe6 na po\xb3\xb9czenie->zarz\xb9dzanie PIN\r\nzapami\xeatywani\r\n------WebKitFormBoundaryyWZOmCEmrqIYb3Zj--\r\n'
def parse_request(request):
    ret = {"url": "", "method": ""}
    if request == b'':
        return ret

    lines = request.split(b'\r\n')

    urls = lines[0].split(b' ')
    ret["url"] = utils.unquote(urls[1]).decode('ascii')
    ret["method"] = utils.unquote(urls[0]).decode('ascii')
    ret["proto"] = utils.unquote(urls[2]).decode('ascii')

    del urls

    headers = {}
    body = b''
    hdr = True
    for line in lines[1:]:
        if hdr:
            if line == b'':
                hdr = False
            else:
                line = utils.unquote(line)
                hdr = line.split(b': ')
                headers[hdr[0].decode('ascii')] = hdr[1].decode('ascii')
        else:
            body += line+b'\r\n'

    ret["headers"] = headers
    ret["body"] = body
    del lines
    del hdr
    return ret


def upload_file(request):
    #Content-Type': 'multipart/form-data; boundary=----WebKitFormBoundaryUdPTIt4xUUzNAXmx
    # -- ----WebKitFormBoundaryUdPTIt4xUUzNAXmx
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
