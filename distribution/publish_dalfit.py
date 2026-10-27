"""Publish already signed APK bytes; no signing material is stored in this repo."""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile,zipfile

BASE=Path('distribution/dalfit-2.0.0')
TAG='dalfit-v2.0.0-build45'
APK='dalfit-2.0.0-build45-release.apk'
APK_SHA='aa5d86106689a8d4ae57e1f01c9371b7f1e035f028aac6e3ba0d1dfece8e55c9'
ZIP_SHA='a7d3d03bb4698bcbe2e7198d6e988c518362f724546fa0d3d76044a27deaaba0'
parts=[BASE/f'build45.zip.part{n:03}' for n in range(1,4)]
assert all(p.is_file() for p in parts),'Missing distribution part'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def gh(*args,check=True):return subprocess.run(['gh',*args],check=check,text=True,capture_output=True)

with tempfile.TemporaryDirectory() as work:
 work=Path(work);archive=work/'verified.zip'
 with archive.open('wb') as out:
  for p in parts:out.write(p.read_bytes())
 assert archive.stat().st_size==23648466 and digest(archive)==ZIP_SHA,'Distribution checksum mismatch'
 target=work/APK
 with zipfile.ZipFile(archive) as z:
  assert set(z.namelist())=={'dalfit-2.0.0.apk','SHA256SUMS.txt'}
  assert z.getinfo('dalfit-2.0.0.apk').file_size==48304088
  target.write_bytes(z.read('dalfit-2.0.0.apk'))
 assert target.stat().st_size==48304088 and digest(target)==APK_SHA,'APK checksum mismatch'
 checksums=work/'SHA256SUMS.txt';checksums.write_text(APK_SHA+'  '+APK+'\n')
 view=gh('release','view',TAG,'--json','assets',check=False)
 if view.returncode:
  gh('release','create',TAG,'--target',os.environ['RELEASE_COMMIT'],'--title','달핏 2.0.0 · 빌드 45','--notes-file',str(BASE/'RELEASE_NOTES.md'),'--latest')
  view=gh('release','view',TAG,'--json','assets')
 assets={a['name'] for a in json.loads(view.stdout)['assets']}
 for p in (target,checksums):
  if p.name in assets:
   downloaded=work/'existing';downloaded.mkdir(exist_ok=True)
   gh('release','download',TAG,'--pattern',p.name,'--dir',str(downloaded))
   assert digest(downloaded/p.name)==digest(p),'Existing release asset differs; refusing to overwrite'
  else:gh('release','upload',TAG,str(p))
 print('Verified APK SHA-256:',APK_SHA)
 print('https://github.com/'+os.environ['GH_REPO']+'/releases/download/'+TAG+'/'+APK)
