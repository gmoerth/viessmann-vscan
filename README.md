# VScan

`Vscan.py` ist ein Python-Scanner fuer Viessmann-Speicherbereiche ueber eine serielle Schnittstelle. Das Skript liest Speicherbloecke aus, zeigt die Daten als Hex- und ASCII-Ausgabe an und markiert Treffer fuer definierte Byte-Muster direkt in der Konsole.

Der aktuelle Stand ist die Datei `Vscan.py`. Die Datei `scan.py` ist eine fruehere, weniger flexible Variante.

## Funktionen

- Verbindung ueber serielle Schnittstelle mit `4800` Baud, `8E1`
- Lesen frei waehlbarer Adressbereiche
- Ausgabe als Hex + ASCII
- Suchmuster in Hex-Notation, z. B. `20 26`
- Alternativmuster fuer denselben Suchlauf
- Zwei Betriebsarten:
  - Blockmodus: Lesen und Ausgabe in Bloecken
  - Rastermodus: Adressweise Abtastung ueber `--step`
- Akustisches Signal und farbige Markierung bei Treffern

## Voraussetzungen

- Python 3
- Paket `pyserial`
- Zugriff auf die passende serielle Schnittstelle
- Ein Geraet bzw. Adapter, der das verwendete Viessmann-Protokoll liefert

Installation von `pyserial`:

```powershell
pip install pyserial
```

## Dateiueberblick

- `Vscan.py`: Hauptprogramm
- `scan.py`: aeltere Ausgangsversion

## Standardwerte in `Vscan.py`

- Port: `/dev/ttyUSB0`
- Startadresse: `0x0000`
- Endadresse: `0xFFFF`
- Blockgroesse: `9`
- Schrittweite: `9`
- Zeilenbreite: `9`
- Pause: `0.0`
- Suchmuster 1: `20 26`
- Suchmuster 2: `19 70`

Wichtig: Unter Windows musst du den Port in der Regel auf etwas wie `COM3` oder `COM4` setzen.

## Aufruf

Beispiel unter Windows:

```powershell
python Vscan.py --port /dev/ttyUSB0
```

Beispiel mit Start- und Endadresse:

```powershell
python Vscan.py --port /dev/ttyUSB0 --start 0x0710 --end 0x2000
```

Beispiel mit eigener Schrittweite und eigenem Suchmuster:

```powershell
python Vscan.py --port /dev/ttyUSB0 --step 1 --pattern "20 26" --pattern-alt "19 70"
```

## Parameter

- `--port`: Serieller Port, z. B. `COM3` oder `/dev/ttyUSB0`
- `--start`: Startadresse, Standardinterpretation ist Hex
- `--end`: Endadresse, exklusiv
- `--block`: Anzahl angeforderter Bytes pro Lesevorgang
- `--step`: Schrittweite je Schleife
- `--line`: Bytes pro Ausgabezeile
- `--pause`: Pause zwischen Lesevorgaengen in Sekunden
- `--pattern`: Hauptsuchmuster als Hex-Bytes
- `--pattern-alt`: Alternatives Suchmuster als Hex-Bytes

Adressformate:

- `0x0710`
- `0710`
- `d:1808`

## Ablauf des Scans

Das Skript arbeitet pro Adresse bzw. Block grob in dieser Reihenfolge:

1. Handshake senden: `0x04`
2. Auf Antwort `0x05` warten
3. Lese-Befehl senden: `0x01 0xF7 <addr_h> <addr_l> <block_size>`
4. Antwortdaten lesen
5. Die letzten `block_size` Bytes als Nutzdaten auswerten
6. Hex- und ASCII-Ausgabe erzeugen
7. Treffer fuer Suchmuster markieren

## Ausgabe

Normale Zeile:

```text
0x0710 | 20 26 30 31 2E 30 39 00 41 |  &01.09.A
```

Trefferzeile:

```text
0x0710 | 20 26 30 31 2E 30 39 00 41 |  &01.09.A  <-- GEFUNDEN!
```

Im Trefferfall wird zusaetzlich ein Signalton ausgegeben.

## Hinweise

- Wenn `--step` ungleich `--block` ist, aktiviert das Skript einen Rastermodus und setzt intern `--line` auf die Blockgroesse.
- Nicht druckbare ASCII-Zeichen werden als `.` dargestellt.
- Das Skript schliesst die serielle Verbindung im `finally`-Block sauber.
