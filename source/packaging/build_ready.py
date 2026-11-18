"""Build the offline root launcher and GitHub-compatible runtime chunks on Windows."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import zipfile

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-zip', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--icon', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    package = out / '_internal'
    assert not package.exists(), package
    assert not (out / 'MediaPress.exe').exists()
    package.mkdir(parents=True)
    args.build_dir.mkdir(parents=True, exist_ok=True)
    parts = []
    archive_hash = hashlib.sha256()
    with args.runtime_zip.open('rb') as source:
        index = 1
        while True:
            first = source.read(1024 * 1024)
            if not first:
                break
            path = package / f'MediaPress.runtime.{index:03d}'
            digest = hashlib.sha256()
            size = 0
            with path.open('wb') as target:
                chunk = first
                while chunk:
                    target.write(chunk)
                    digest.update(chunk)
                    archive_hash.update(chunk)
                    size += len(chunk)
                    chunk = source.read(min(1024 * 1024, 90 * 1024 * 1024 - size)) if size < 90 * 1024 * 1024 else b''
            parts.append({'Name': path.name, 'Size': size, 'Sha256': digest.hexdigest()})
            index += 1
    with zipfile.ZipFile(args.runtime_zip) as archive:
        files = [f for f in archive.infolist() if not f.is_dir()]
        roots = {f.filename.split('/')[0] for f in files}
        assert len(roots) == 1
        root = roots.pop()
        critical_suffixes = ('/MediaPress.exe', '/python314.dll', '/Qt6Core.dll', '/Qt6WebEngineCore.dll', '/ffmpeg.exe', '/ffprobe.exe')
        critical = [{'Path': f.filename, 'Size': f.file_size} for f in files if f.filename.endswith(critical_suffixes)]
        assert len(critical) >= 5, critical
    manifest = {'Version': '2.1.0', 'ArchiveRoot': root, 'ArchiveSha256': archive_hash.hexdigest(),
                'UncompressedBytes': sum(f.file_size for f in files), 'Parts': parts, 'CriticalFiles': critical}
    raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    (package / 'runtime.json').write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    launcher = args.build_dir / 'ReadyLauncher.cs'
    launcher.write_text((Path(__file__).parent / 'ReadyLauncher.cs').read_text(encoding='utf-8').replace('@@MANIFEST_SHA@@', digest), encoding='utf-8')
    app_manifest = args.build_dir / 'launcher.manifest'
    app_manifest.write_text('''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <assemblyIdentity version="2.1.0.0" processorArchitecture="amd64" name="MediaPress.Ready" type="win32"/>
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3"><security><requestedPrivileges><requestedExecutionLevel level="asInvoker" uiAccess="false"/></requestedPrivileges></security></trustInfo>
  <application xmlns="urn:schemas-microsoft-com:asm.v3"><windowsSettings>
    <longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware>
    <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true</dpiAware>
  </windowsSettings></application>
</assembly>
''', encoding='utf-8')
    compiler = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler), '/nologo', '/target:winexe', '/platform:x64', '/optimize+',
                    '/out:' + str(out / 'MediaPress.exe'), '/win32icon:' + str(args.icon.resolve()),
                    '/win32manifest:' + str(app_manifest.resolve()),
                    '/reference:System.IO.Compression.dll', '/reference:System.Runtime.Serialization.dll',
                    '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll', str(launcher.resolve())], check=True)
    print(json.dumps({'parts': len(parts), 'bytes': sum(p['Size'] for p in parts), 'manifest_sha256': digest,
                      'exe': str(out / 'MediaPress.exe'), 'archive_sha256': archive_hash.hexdigest()}), flush=True)

if __name__ == '__main__':
    main()
