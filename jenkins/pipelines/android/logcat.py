import argparse
import os
import re
import subprocess
import time


def adb_logcat(adb_path, device_serial):
    test_start = re.compile(">>>>>>>>>> (\\w+)")
    test_name = None
    out_file = None
    
    cmd = [adb_path]
    if device_serial:
        cmd = cmd + ["-s", device_serial]
    cmd.append("logcat")

    subprocess.run(cmd + ["-b", "main", "-G", "32M"])

    with subprocess.Popen(cmd, stdout=subprocess.PIPE) as log:
        while True:
            line = log.stdout.readline()
            if not line:
                break

            line = line.decode("utf-8")

            if out_file is not None:
                out_file.write(line)

                if f"<<<<<<<<<< {test_name}" in line:
                    out_file.close()
                    out_file = None
                    test_name = None

            else:
                m = test_start.search(line)
                if m:
                    test_name = m.group(1)
                    out_file = open(f"{test_name}.log", "w")
                    out_file.write(line)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Logcat')
    parser.add_argument('-a', '--android', type=str, help='Android HOME')
    parser.add_argument('-s', '--serial', help='Device serial number')

    args = parser.parse_args()

    adb_path = "adb" if not args.android else f"{args.android}/platform-tools/adb"

    log_dir = f"logs_{int(time.time())}"
    os.mkdir(log_dir)
    os.chdir(log_dir)
    
    adb_logcat(adb_path, args.serial)
