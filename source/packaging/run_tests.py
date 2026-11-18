from pathlib import Path
import argparse
import os
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--build-dir', type=Path, required=True)
args = parser.parse_args()
args.build_dir.mkdir(parents=True, exist_ok=True)
compiler = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
here = Path(__file__).resolve().parent
exe = (args.build_dir / 'LauncherTests.exe').resolve()
subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64', '/optimize+', '/main:LauncherTests',
                '/out:' + str(exe), '/reference:System.IO.Compression.dll', '/reference:System.Runtime.Serialization.dll',
                '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll',
                str(here / 'ReadyLauncher.cs'), str(here / 'LauncherTests.cs')], check=True)
subprocess.run([str(exe)], check=True)
