import utils

def get_template(temperatura):
    temp = utils.get_config("piec_temperatura")
    times = utils.get_config("piec_czasy", {})
    last = utils.get_config("piec_ostatnia_aktualizacja", '')
    tm = ''
    czas = utils.czas()
    for t in times:
        tm += t + ' - ' + str(times[t]) + '\n'
    html = """<!DOCTYPE html>
<head>
    <meta charset='UTF-8'>
</head>
<title>Kontrola pieca</title>
<body>
  <h3>Kontrola pieca</h3>
  <p>Czas na urządzeniu: %s</p>
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
""" % (czas, str(temperatura), last, str(temp), tm)
    return html
