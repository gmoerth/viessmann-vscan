import argparse
import serial
import time
import sys

# --- DEFAULTS (können per CLI überschrieben werden) ---
DEFAULT_SERIAL_PORT = "/dev/ttyUSB0"
DEFAULT_START_ADDR = 0x0000
DEFAULT_END_ADDR = 0xFFFF

DEFAULT_BLOCK_SIZE = 9
DEFAULT_LINE_WIDTH = 9
DEFAULT_STEP_SIZE = 9
DEFAULT_PAUSE = 0.0

DEFAULT_SEARCH_PATTERN = "20 26"
DEFAULT_SEARCH_PATTERN_ALT = "19 70"

# ANSI Farben für die Konsole
GREEN = "\033[92m"
BOLD = "\033[1m"
ENDC = "\033[0m"
BEEP = "\a"


def parse_hex_int(s: str) -> int:
    """
    Accepts: '0x710', '710' (interpreted as hex), or decimal with 'd:' prefix like 'd:1234'
    Default interpretation without prefix is HEX (more convenient for addresses).
    """
    s = s.strip().lower()
    if s.startswith("d:"):
        return int(s[2:], 10)
    if s.startswith("0x"):
        return int(s, 16)
    # default: hex
    return int(s, 16)


def parse_pattern(s: str) -> bytes:
    """'1E 84' -> bytes([0x1E, 0x84])"""
    parts = s.strip().split()
    return bytes(int(p, 16) for p in parts)


def bytes_to_ascii(bs: bytes) -> str:
    return "".join(chr(b) if 32 <= b <= 126 else "." for b in bs)


def format_hex_line(bs: bytes, width: int) -> str:
    hex_bytes = " ".join(f"{b:02X}" for b in bs)
    pad_len = (width * 3 - 1) - len(hex_bytes)
    if pad_len > 0:
        hex_bytes += " " * pad_len
    return hex_bytes


def scan_with_search(
    serial_port: str,
    start_addr: int,
    end_addr: int,
    block_size: int,
    line_width: int,
    step_size: int,
    pause_blocks: float,
    pat1: bytes,
    pat2: bytes,
):
    # Regel: wenn Rastermodus (STEP != BLOCK), dann LINE_WIDTH = BLOCK (eine Zeile pro Adresse)
    if step_size != block_size and line_width != block_size:
        print(
            f"Hinweis: --step({step_size}) != --block({block_size}) -> setze --line={block_size} (eine Zeile pro Adresse)"
        )
        line_width = block_size

    ser = None
    pending = bytearray()
    pending_addr = None
    prev_tail = b""

    try:
        ser = serial.Serial(
            port=serial_port,
            baudrate=4800,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            timeout=2.0,
        )

        current_addr = start_addr
        mode = "RASTER" if step_size != block_size else "BLOCK"
        print(f"--- STARTE SUCHE NACH {pat1.hex(' ').upper()} AB 0x{start_addr:04X} ---")
        print(
            f"--- Modus: {mode} | block={block_size} | step={step_size} | line={line_width} | range=0x{start_addr:04X}..0x{end_addr:04X} ---"
        )

        while current_addr < end_addr:
            # 1) Handshake (04 -> 05)
            ser.write(bytes([0x04]))
            time.sleep(0.1)
            ser.reset_input_buffer()

            sync = ser.read(1)
            if sync != bytes([0x05]):
                print(f"0x{current_addr:04X} | Kein Sync (05 fehlt).")
                current_addr += step_size
                time.sleep(pause_blocks)
                continue

            # 2) Block anfordern
            addr_h = (current_addr >> 8) & 0xFF
            addr_l = current_addr & 0xFF
            cmd = bytes([0x01, 0xF7, addr_h, addr_l, block_size])
            ser.write(cmd)
            ser.flush()

            # 3) Warten auf Daten
            time.sleep(0.1)

            if not ser.in_waiting:
                print(f"Fehler bei 0x{current_addr:04X}: Keine Daten.")
                current_addr += step_size
                time.sleep(pause_blocks)
                continue

            raw_data = ser.read(ser.in_waiting)
            if len(raw_data) < block_size:
                print(f"Fehler bei 0x{current_addr:04X}: Nur {len(raw_data)} Bytes empfangen.")
                current_addr += step_size
                time.sleep(pause_blocks)
                continue

            data = raw_data[-block_size:]

            # --- RASTERMODUS: pro Adresse genau eine Zeile ---
            if step_size != block_size:
                line_bytes = data[:line_width]  # line_width == block_size erzwungen
                window = prev_tail + line_bytes
                found = False

                for pat in (pat1, pat2):
                    start = 0
                    while True:
                        idx = window.find(pat, start)
                        if idx == -1:
                            break
                        if idx < len(prev_tail) + line_width and (idx + len(pat)) > len(prev_tail):
                            found = True
                            break
                        start = idx + 1
                    if found:
                        break

                hex_part = format_hex_line(line_bytes, line_width)
                ascii_part = bytes_to_ascii(line_bytes)

                if found:
                    sys.stdout.write(BEEP)
                    print(f"{GREEN}{BOLD}0x{current_addr:04X} | {hex_part} | {ascii_part}  <-- GEFUNDEN!{ENDC}")
                else:
                    print(f"0x{current_addr:04X} | {hex_part} | {ascii_part}")

                prev_tail = line_bytes[-1:]

            # --- BLOCKMODUS: wie bisher puffern + in line_width Schritten drucken ---
            else:
                if pending_addr is None:
                    pending_addr = current_addr

                pending.extend(data)

                while len(pending) >= line_width:
                    line_bytes = bytes(pending[:line_width])
                    line_addr = pending_addr

                    window = prev_tail + line_bytes
                    found = False

                    for pat in (pat1, pat2):
                        start = 0
                        while True:
                            idx = window.find(pat, start)
                            if idx == -1:
                                break
                            if idx < len(prev_tail) + line_width and (idx + len(pat)) > len(prev_tail):
                                found = True
                                break
                            start = idx + 1
                        if found:
                            break

                    hex_part = format_hex_line(line_bytes, line_width)
                    ascii_part = bytes_to_ascii(line_bytes)

                    if found:
                        sys.stdout.write(BEEP)
                        print(f"{GREEN}{BOLD}0x{line_addr:04X} | {hex_part} | {ascii_part}  <-- GEFUNDEN!{ENDC}")
                    else:
                        print(f"0x{line_addr:04X} | {hex_part} | {ascii_part}")

                    prev_tail = line_bytes[-1:]
                    del pending[:line_width]
                    pending_addr += line_width

            current_addr += step_size
            time.sleep(pause_blocks)
            sys.stdout.flush()

    except Exception as e:
        print(f"\nFehler: {e}")
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        print("\nSuche beendet.")


def main():
    ap = argparse.ArgumentParser(
        description="Viessmann Speicher-Scanner (Hex+ASCII Ausgabe, optional Rastermodus über --step)"
    )
    ap.add_argument("--port", default=DEFAULT_SERIAL_PORT, help=f"Serial Port (default: {DEFAULT_SERIAL_PORT})")

    ap.add_argument("--start", default=f"0x{DEFAULT_START_ADDR:04X}", type=parse_hex_int,
                    help="Startadresse (hex default). Beispiele: 0x0710, 0710, d:1808")
    ap.add_argument("--end", default=f"0x{DEFAULT_END_ADDR:04X}", type=parse_hex_int,
                    help="Endadresse (exklusiv, hex default). Beispiele: 0x2000, 2000, d:8192")

    ap.add_argument("--block", type=int, default=DEFAULT_BLOCK_SIZE,
                    help=f"Angeforderte Bytes pro Read (default: {DEFAULT_BLOCK_SIZE})")
    ap.add_argument("--step", type=int, default=DEFAULT_STEP_SIZE,
                    help=f"Schrittweite je Schleife (default: {DEFAULT_STEP_SIZE}). 1 = jede Adresse (Raster).")
    ap.add_argument("--line", type=int, default=DEFAULT_LINE_WIDTH,
                    help=f"Bytes pro Ausgabezeile (default: {DEFAULT_LINE_WIDTH}). "
                         f"Wenn --step != --block wird automatisch --line=--block gesetzt.")

    ap.add_argument("--pause", type=float, default=DEFAULT_PAUSE,
                    help=f"Pause zwischen Reads in Sekunden (default: {DEFAULT_PAUSE})")

    ap.add_argument("--pattern", default=DEFAULT_SEARCH_PATTERN,
                    help=f"Suchpattern als Hexbytes mit Space (default: '{DEFAULT_SEARCH_PATTERN}')")
    ap.add_argument("--pattern-alt", default=DEFAULT_SEARCH_PATTERN_ALT,
                    help=f"Alternatives Suchpattern (default: '{DEFAULT_SEARCH_PATTERN_ALT}')")

    args = ap.parse_args()

    if args.block <= 0 or args.step <= 0 or args.line <= 0:
        raise SystemExit("--block/--step/--line müssen > 0 sein")

    if args.start < 0 or args.end < 0 or args.end <= args.start:
        raise SystemExit("--end muss größer als --start sein")

    pat1 = parse_pattern(args.pattern)
    pat2 = parse_pattern(args.pattern_alt)

    scan_with_search(
        serial_port=args.port,
        start_addr=args.start,
        end_addr=args.end,
        block_size=args.block,
        line_width=args.line,
        step_size=args.step,
        pause_blocks=args.pause,
        pat1=pat1,
        pat2=pat2,
    )


if __name__ == "__main__":
    main()
