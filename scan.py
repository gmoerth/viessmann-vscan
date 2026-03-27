import serial
import time
import sys

# --- KONFIGURATION ---
SERIAL_PORT = '/dev/ttyUSB0'
START_ADDR = 0x0000
END_ADDR = 0xFFFF

BLOCK_SIZE = 9        # angeforderte Bytes pro Read-Command
LINE_WIDTH = 9         # Ausgabe pro Zeile (wie im Hex-Editor)
PAUSE_BLOCKS = 0.0

SEARCH_PATTERN = "1E 84"       # '20 26' für BLOCK_SIZE=8 Datum jahr 2026
SEARCH_PATTERN_ALT = "84 1E"

# ANSI Farben für die Konsole
GREEN = '\033[92m'
BOLD = '\033[1m'
ENDC = '\033[0m'
BEEP = '\a'  # System Beep


def parse_pattern(s: str):
    """'1E 84' -> bytes([0x1E, 0x84])"""
    parts = s.strip().split()
    return bytes(int(p, 16) for p in parts)


PAT1 = parse_pattern(SEARCH_PATTERN)
PAT2 = parse_pattern(SEARCH_PATTERN_ALT)


def bytes_to_ascii(bs: bytes) -> str:
    # printable ASCII 0x20..0x7E, sonst '.'
    return ''.join(chr(b) if 32 <= b <= 126 else '.' for b in bs)


def format_hex_line(bs: bytes, width: int) -> str:
    # Hex-Spalte auf feste Breite (padding), damit ASCII sauber ausgerichtet bleibt
    hex_bytes = ' '.join(f"{b:02X}" for b in bs)
    # Jede Byte-Darstellung hat 2 Zeichen, plus 1 Space dazwischen => width*3 - 1
    pad_len = (width * 3 - 1) - len(hex_bytes)
    if pad_len > 0:
        hex_bytes += ' ' * pad_len
    return hex_bytes


def scan_with_search():
    ser = None

    # Puffer für "erst drucken wenn 8 Bytes da sind"
    pending = bytearray()
    pending_addr = None  # Adresse des ersten Bytes im pending

    # Für Pattern-Überlauf über Zeilengrenze: letztes Byte der vorherigen Ausgabezeile merken
    prev_tail = b''

    try:
        ser = serial.Serial(
            port=SERIAL_PORT, baudrate=4800,
            bytesize=serial.EIGHTBITS, parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE, timeout=2.0
        )

        current_addr = START_ADDR
        print(f"--- STARTE SUCHE NACH {SEARCH_PATTERN} AB {hex(START_ADDR)} ---")
        print(f"--- Ausgabe: {LINE_WIDTH} Bytes pro Zeile (Hex + ASCII) ---")

        while current_addr < END_ADDR:
            # 1) Handshake (04 -> 05)
            ser.write(bytes([0x04]))
            time.sleep(0.1)
            ser.reset_input_buffer()

            sync = ser.read(1)
            if sync != bytes([0x05]):
                print(f"0x{current_addr:04X} | Kein Sync (05 fehlt).")
                current_addr += BLOCK_SIZE
                time.sleep(PAUSE_BLOCKS)
                continue

            # 2) Block anfordern
            addr_h = (current_addr >> 8) & 0xFF
            addr_l = current_addr & 0xFF
            cmd = bytes([0x01, 0xF7, addr_h, addr_l, BLOCK_SIZE])
            ser.write(cmd)
            ser.flush()

            # 3) Warten auf Daten
            time.sleep(0.1)

            if not ser.in_waiting:
                print(f"Fehler bei {hex(current_addr)}: Keine Daten.")
                current_addr += BLOCK_SIZE
                time.sleep(PAUSE_BLOCKS)
                continue

            raw_data = ser.read(ser.in_waiting)
            # wie vorher: die letzten BLOCK_SIZE Bytes als Nutzdaten nehmen
            # (wenn das Protokoll vorne Header/Status mitliefert)
            if len(raw_data) < BLOCK_SIZE:
                print(f"Fehler bei {hex(current_addr)}: Nur {len(raw_data)} Bytes empfangen.")
                current_addr += BLOCK_SIZE
                time.sleep(PAUSE_BLOCKS)
                continue

            data = raw_data[-BLOCK_SIZE:]

            # 4) Puffer füttern, erst drucken wenn 8 Bytes zusammen sind
            if pending_addr is None:
                pending_addr = current_addr  # Startadresse für den Buffer

            pending.extend(data)

            # Solange ganze Zeilen verfügbar sind -> ausgeben
            while len(pending) >= LINE_WIDTH:
                line_bytes = bytes(pending[:LINE_WIDTH])
                line_addr = pending_addr

                # Pattern-Check inkl. Boundary: prev_tail + aktuelle Zeile
                # Wenn Pattern in diesem Fenster vorkommt UND mindestens ein Byte davon in der aktuellen Zeile liegt,
                # markieren wir die Zeile.
                window = prev_tail + line_bytes
                found = False

                # Suche beide Pattern
                for pat in (PAT1, PAT2):
                    start = 0
                    while True:
                        idx = window.find(pat, start)
                        if idx == -1:
                            break
                        # idx bezieht sich auf window; prev_tail hat Länge len(prev_tail)
                        # Pattern berührt aktuelle Zeile, wenn idx < len(prev_tail)+LINE_WIDTH und idx+len(pat) > len(prev_tail)
                        if idx < len(prev_tail) + LINE_WIDTH and (idx + len(pat)) > len(prev_tail):
                            found = True
                            break
                        start = idx + 1
                    if found:
                        break

                hex_part = format_hex_line(line_bytes, LINE_WIDTH)
                ascii_part = bytes_to_ascii(line_bytes)

                if found:
                    sys.stdout.write(BEEP)
                    print(f"{GREEN}{BOLD}0x{line_addr:04X} | {hex_part} | {ascii_part}  <-- GEFUNDEN!{ENDC}")
                else:
                    print(f"0x{line_addr:04X} | {hex_part} | {ascii_part}")

                # Tail für Boundary-Erkennung: 1 Byte reicht für 2-Byte Pattern
                prev_tail = line_bytes[-1:]

                # Puffer „verbrauchen“
                del pending[:LINE_WIDTH]
                pending_addr += LINE_WIDTH

            current_addr += BLOCK_SIZE
            time.sleep(PAUSE_BLOCKS)
            sys.stdout.flush()

        # Optional: Restbytes am Ende NICHT ausgeben (weil Wunsch: erst bei 8 Bytes drucken)
        # Wenn du am Ende trotzdem den Rest sehen willst, sag Bescheid, dann machen wir einen "Flush".

    except Exception as e:
        print(f"\nFehler: {e}")
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        print("\nSuche beendet.")


if __name__ == "__main__":
    scan_with_search()
