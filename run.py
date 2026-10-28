"""Portable local setup/launcher. python run.py setup | python run.py | python run.py test"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
NPM = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')

def call(args, folder=ROOT):
    subprocess.run([str(a) for a in args], cwd=folder, check=True)

def main():
    command = sys.argv[1] if len(sys.argv)>1 else 'start'
    if command == 'setup':
        if not NPM:
            raise SystemExit('Install Node.js 22.12+ (LTS recommended), then reopen your terminal.')
        if not PYTHON.exists():
            call([sys.executable, '-m', 'venv', ROOT/'.venv'])
        call([PYTHON,'-m','pip','install','-r',ROOT/'backend/requirements.txt'])
        call([PYTHON,'-m','flask','--app','app','db','upgrade'], ROOT/'backend')
        call([PYTHON,'-m','flask','--app','app','init-demo'], ROOT/'backend')
        call([NPM,'ci'], ROOT/'frontend')
        print('\nSetup complete. Run: python run.py (macOS: python3 run.py)')
    elif command == 'test':
        call([PYTHON,'-m','pytest','-q'], ROOT/'backend')
        call([NPM,'run','build'], ROOT/'frontend')
    elif command == 'start':
        if not PYTHON.exists() or not (ROOT/'frontend/node_modules').exists():
            raise SystemExit('Run setup first: python3 run.py setup (Windows: py run.py setup)')
        if not NPM:
            raise SystemExit('Node/npm is not on PATH.')
        processes=[]
        failed = False
        try:
            processes.append(subprocess.Popen([str(PYTHON),'-m','flask','--app','app','run','--host','127.0.0.1','--port','5001'],cwd=ROOT/'backend'))
            processes.append(subprocess.Popen([NPM,'run','dev'],cwd=ROOT/'frontend'))
            print('\nAdmin: http://127.0.0.1:5173/admin\nSwagger: http://127.0.0.1:5001/api/docs/\nPress Ctrl+C to stop both servers.\n',flush=True)
            while all(p.poll() is None for p in processes):
                time.sleep(.5)
            failed = any(p.poll() not in (None, 0) for p in processes)
        except KeyboardInterrupt:
            pass
        finally:
            for p in processes:
                if p.poll() is None:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(p.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        p.terminate()
            for p in processes:
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
        if failed:
            raise SystemExit('A server failed. Check the messages above (including whether ports 5001/5173 are already occupied).')
    else:
        raise SystemExit('Use: python run.py [setup|start|test]')

if __name__ == '__main__':
    main()
