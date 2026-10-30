# tc_runner.py — Generic template for GHS Multi `python -b -f` invocation
#
# INVOKE from .rc:  python -b -f tc_runner.py <TC_ID> <RESULT_DIR_WIN>
# RULES:
#   1. NEVER use print() — not captured in -R log
#   2. NEVER use __file__ — unreliable with -b -f
#   3. NEVER put ; go in rolling breakpoint callback — rolling auto-continues
#   4. Always resume with debugger.RunCommands("target gc") — not "go"
#   5. Pass result dir as argv[2] so script is project-agnostic

import sys, time

tc         = sys.argv[1] if len(sys.argv) > 1 else "TC01"
result_dir = sys.argv[2] if len(sys.argv) > 2 else "."
_rf        = result_dir + "\\" + tc + "_result.txt"
open(_rf, "w").close()  # truncate fresh

def log(msg):
    with open(_rf, "a") as f: f.write(msg + "\n")
    debugger.RunCommands("mprintf(\"PY:" + msg.replace('"',"'") + "\\n\")")

def cmd(s):
    debugger.RunCommands(s)

def read_byte(addr):
    debugger.RunCommands("m7_0 target mr 1 {0:#010x}".format(addr))
    try: return int(debugger.cmdExecOutput.split(":")[-1].strip(), 16)
    except: return -1

def write_byte(addr, val):
    debugger.RunCommands("m7_0 *(unsigned char*){0:#010x} = {1}".format(addr, val))

# Rolling breakpoints — NO "; go" (auto-continues already)
cmd("m7_0 hardbrk rolling MY_FUNC { mprintf(\"HIT r0=0x%x\\n\", $r0) }")

log("=== " + tc + " START ===")
# 1. inject: write_byte(ADDRESS, VALUE)
# 2. log PRE state: read_byte(ADDRESS)
# 3. resume: cmd("target gc")
# 4. wait:   time.sleep(SECONDS)
# 5. log POST state: read_byte(ADDRESS)
log("=== " + tc + " END ===")
