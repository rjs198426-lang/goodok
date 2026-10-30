"""Publish verified signed bytes using the existing release workflow; no signing material in GitHub."""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile,re,zipfile
import bsdiff4
BASE=Path('distribution/dalfit-2.1.2');CONFIG=json.loads((BASE/'RELEASE.json').read_text());TAG=CONFIG['tag']
def digest(data):return hashlib.sha256(data).hexdigest()
def gh(*args,check=True):return subprocess.run(['gh',*args],check=check,text=True,capture_output=True)
def verify_assets(apk,source):
 # Required release gate: a signed APK can still be unusable if native routing blocks a module.
 with zipfile.ZipFile(source) as src,zipfile.ZipFile(apk) as app:
  activity=src.read('dalfit-android/app/src/main/java/kr/goodok/note/MainActivity.java').decode()
  types={}
  for group,mime in re.findall(r'((?:\s*case\s+"[^"]+"\s*:\s*)+)mime\s*=\s*"([^"]+)"\s*;\s*break\s*;',activity):
   for path in re.findall(r'case\s+"([^"]+)"',group):types[path]=mime
  expected={'.js':('text/javascript','application/javascript'),'.html':('text/html',),'.css':('text/css',),'.svg':('image/svg+xml',),'.woff2':('font/woff2',),'.png':('image/png',),'.webp':('image/webp',),'.jpg':('image/jpeg',)}
  checked=0;dex=b''.join(app.read(n) for n in app.namelist() if n.endswith('.dex'))
  for name in app.namelist():
   if not name.startswith('assets/') or Path(name).suffix not in expected:continue
   route='/'+name.removeprefix('assets/')
   assert types.get(route) in expected[Path(name).suffix], 'Android blocks packaged asset '+route
   assert route.encode() in dex, 'Compiled Android routing omits '+route
   assert app.read(name)==src.read('dalfit-android/app/src/main/'+name), 'Source/APK asset mismatch '+route
   checked+=1
  assert checked>80,'Missing packaged web assets'
  print('Android asset route/MIME/source gate:',checked,'assets verified')
with tempfile.TemporaryDirectory() as temp:
 work=Path(temp);assets=[]
 for item in CONFIG['assets']:
  gh('release','download',CONFIG['baseTag'],'--pattern',item['baseName'],'--dir',str(work))
  old=(work/item['baseName']).read_bytes();assert digest(old)==item['baseSha256'],'Base checksum mismatch'
  patch=b''.join((BASE/name).read_bytes() for name in item['parts']);assert len(patch)==item['patchBytes'] and digest(patch)==item['patchSha256'],'Patch checksum mismatch'
  data=bsdiff4.patch(old,patch);assert len(data)==item['bytes'] and digest(data)==item['sha256'],'Release checksum mismatch'
  target=work/item['name'];target.write_bytes(data);assets.append(target)
 verify_assets(assets[0],assets[1])
 checksums=work/'SHA256SUMS.txt';checksums.write_text(''.join(item['sha256']+'  '+item['name']+'\n' for item in CONFIG['assets']));assets.extend((checksums,BASE/'HOTFIX_NOTES.md',BASE/'VALIDATION.json',BASE/'STARTUP_VALIDATION.json'))
 view=gh('release','view',TAG,'--json','assets',check=False)
 if view.returncode:
  gh('release','create',TAG,'--target',os.environ['RELEASE_COMMIT'],'--title','달핏 2.1.2 · 빌드 51','--notes-file',str(BASE/'RELEASE_NOTES.md'),'--latest');view=gh('release','view',TAG,'--json','assets')
 existing={a['name'] for a in json.loads(view.stdout)['assets']}
 for p in assets:
  if p.name in existing:
   folder=work/'existing';folder.mkdir(exist_ok=True);gh('release','download',TAG,'--pattern',p.name,'--dir',str(folder));assert digest((folder/p.name).read_bytes())==digest(p.read_bytes()),'Existing asset differs; refusing overwrite'
  else:gh('release','upload',TAG,str(p))
 print('Verified release',TAG)
 for item in CONFIG['assets']:print(item['name'],item['sha256'])
