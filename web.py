import utils
import json
import sensors
import utime


def send_file(socket, file_name, mode='r'):
    try:
        while utils.file_locked(file_name):
            utime.sleep_ms(1)

        utils.lock_file(file_name)

        with open(file_name, mode) as fi:
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


def get_header(mime_type):
    return "HTTP/1.1 200OK\n" + "Content-Type: %s\n" % mime_type + "Connection: close\n\n"


def handle_api(socket, request):
    if request["url"].find("/api/dane.json") > -1:
        termometr = sensors.Sensory()

        dane = utils.get_data()
        print(dane)
        dane["termometr"] = termometr.pomiar_temperatury()

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
        p = json.loads(request["body"])
        print(utils.config)
        utils.config.update(p)
        print(utils.config)
        utils.save_config()
        socket.sendall(get_header('application/json'))
        socket.sendall('OK')
    elif request["url"].find("/api/logs") > -1:
        socket.sendall(get_header('text/plain'))
        send_file(socket, 'log.txt', 'r')
    elif request["url"].find("/api/hist_piec") > -1:
        socket.sendall(get_header('text/plain'))
        send_file(socket, 'piec.hist', 'r')
    elif request["url"].find("/api/hist_termo") > -1:
        socket.sendall(get_header('text/plain'))
        send_file(socket, 'termometr.hist', 'r')
    elif request["url"].find("/api/chart.json") > -1:
        socket.sendall(get_header('application/json'))
        send_chart_data(socket)
    return True


def send_chart_data(socket):
    for i in range(1, 3):
        if i == 1:
            file_name = 'termometr.hist'
            data = """[{"name": "Termometr", "data": ["""
            termometr = sensors.Sensory()
            curr = termometr.pomiar_temperatury()
            sqr = False
        else:
            file_name = 'piec.hist'
            data = """{"name": "Piec", "data": ["""
            curr = int(utils.get_config("piec_temperatura", 40))
            sqr = True

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


_hextobyte_cache = None


def unquote(string):
    """unquote('abc%20def') -> b'abc def'."""
    global _hextobyte_cache

    # Note: strings are encoded as UTF-8. This is only an issue if it contains
    # unescaped non-ASCII characters, which URIs should not.
    if not string:
        return b''

    if isinstance(string, str):
        string = string.encode('utf-8')

    bits = string.split(b'%')
    if len(bits) == 1:
        return string

    res = [bits[0]]
    append = res.append

    # Build cache for hex to char mapping on-the-fly only for codes
    # that are actually used
    if _hextobyte_cache is None:
        _hextobyte_cache = {}

    for item in bits[1:]:
        try:
            code = item[:2]
            char = _hextobyte_cache.get(code)
            if char is None:
                char = _hextobyte_cache[code] = bytes([int(code, 16)])
            append(char)
            append(item[2:])
        except KeyError:
            append(b'%')
            append(item)

    return b''.join(res)


def parse_request(request):
    ret = {"url": "", "method": ""}
    if request == b'':
        return ret

    lines = request.split(b'\r\n')

    urls = lines[0].split(b' ')
    ret["url"] = unquote(urls[1]).decode('ascii')
    ret["method"] = unquote(urls[0]).decode('ascii')
    ret["proto"] = unquote(urls[2]).decode('ascii')
    headers = {}
    body = b''
    hdr_end = False
    for line in lines[1:]:
        line = unquote(line)
        if line == b'':
            hdr_end = True
        else:
            if hdr_end:
                body = line
            else:
                hdr = line.split(b': ')
                headers[hdr[0].decode('ascii')] = hdr[1].decode('ascii')

    ret["headers"] = headers
    ret["body"] = body.decode('ascii')
    return ret
