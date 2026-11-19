import glob, sys, time, serial
log = open(sys.argv[1], 'ab', buffering=0)
end = time.time() + float(sys.argv[2])
while time.time() < end:
    ports = glob.glob('/dev/cu.usbmodem*')
    if not ports: time.sleep(0.5); continue
    try:
        s = serial.Serial(ports[0], 115200, timeout=0.5)
        log.write(f'\n=== open {ports[0]} {time.strftime("%H:%M:%S")} ===\n'.encode())
        while time.time() < end:
            d = s.read(4096)
            if d: log.write(d)
    except Exception as e:
        log.write(f'\n=== {e!r} {time.strftime("%H:%M:%S")} ===\n'.encode()); time.sleep(0.5)
