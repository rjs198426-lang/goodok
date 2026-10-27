"""Publish already signed APK bytes; no signing material is stored in this repo."""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile,zipfile

BASE=Path('distribution/dalfit-2.0.2')
TAG='dalfit-v2.0.2-build47'
APK='dalfit-2.0.2-build47-release.apk'
APK_SHA='ff5c0ec4e396cacc08fcc16feb0323fa5bbe6baf1cc31c97be5fd6bafe094b66'
ZIP_SHA='2e681a77e5b2f197852e78735b4ddfe9f787512dd715324e8df6870d029f753d'
parts=[BASE/f'build47.zip.part{n:03}' for n in range(1,4)]
assert all(p.is_file() for p in parts),'Missing distribution part'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def gh(*args,check=True):return subprocess.run(['gh',*args],check=check,text=True,capture_output=True)

with tempfile.TemporaryDirectory() as work:
 work=Path(work);archive=work/'verified.zip'
 with archive.open('wb') as out:
  for p in parts:out.write(p.read_bytes())
 assert archive.stat().st_size==23647383 and digest(archive)==ZIP_SHA,'Distribution checksum mismatch'
 target=work/APK
 with zipfile.ZipFile(archive) as z:
  assert set(z.namelist())=={APK,'SHA256SUMS.txt'}
  assert z.getinfo(APK).file_size==48304340
  target.write_bytes(z.read(APK))
 assert target.stat().st_size==48304340 and digest(target)==APK_SHA,'APK checksum mismatch'
 checksums=work/'SHA256SUMS.txt';checksums.write_text(APK_SHA+'  '+APK+'\n')
 view=gh('release','view',TAG,'--json','assets',check=False)
 if view.returncode:
  gh('release','create',TAG,'--target',os.environ['RELEASE_COMMIT'],'--title','달핏 2.0.2 · 빌드 47','--notes-file',str(BASE/'RELEASE_NOTES.md'),'--latest')
  view=gh('release','view',TAG,'--json','assets')
 assets={a['name'] for a in json.loads(view.stdout)['assets']}
 source=BASE/'dalfit-android-source-2.0.2-build47.zip'
 assert digest(source)=='14467468f0bbe5474fa35850b791d74da5ed4814a056287c7cc305a2449d1b8d','Source checksum mismatch'
 for p in (target,checksums,source,BASE/'UI_NOTES.md',BASE/'VALIDATION.json'):
  if p.name in assets:
   downloaded=work/'existing';downloaded.mkdir(exist_ok=True)
   gh('release','download',TAG,'--pattern',p.name,'--dir',str(downloaded))
   assert digest(downloaded/p.name)==digest(p),'Existing release asset differs; refusing to overwrite'
  else:gh('release','upload',TAG,str(p))
 print('Verified APK SHA-256:',APK_SHA)
 print('https://github.com/'+os.environ['GH_REPO']+'/releases/download/'+TAG+'/'+APK)
