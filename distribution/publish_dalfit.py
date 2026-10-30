"""Publish verified signed bytes using the existing release workflow; no signing material in GitHub."""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile
import bsdiff4
BASE=Path('distribution/dalfit-2.1.1');CONFIG=json.loads((BASE/'RELEASE.json').read_text());TAG=CONFIG['tag']
def digest(data):return hashlib.sha256(data).hexdigest()
def gh(*args,check=True):return subprocess.run(['gh',*args],check=check,text=True,capture_output=True)
with tempfile.TemporaryDirectory() as temp:
 work=Path(temp);assets=[]
 for item in CONFIG['assets']:
  gh('release','download',CONFIG['baseTag'],'--pattern',item['baseName'],'--dir',str(work))
  old=(work/item['baseName']).read_bytes();assert digest(old)==item['baseSha256'],'Base checksum mismatch'
  patch=b''.join((BASE/name).read_bytes() for name in item['parts']);assert len(patch)==item['patchBytes'] and digest(patch)==item['patchSha256'],'Patch checksum mismatch'
  data=bsdiff4.patch(old,patch);assert len(data)==item['bytes'] and digest(data)==item['sha256'],'Release checksum mismatch'
  target=work/item['name'];target.write_bytes(data);assets.append(target)
 checksums=work/'SHA256SUMS.txt';checksums.write_text(''.join(item['sha256']+'  '+item['name']+'\n' for item in CONFIG['assets']));assets.extend((checksums,BASE/'ICON_NOTES.md',BASE/'VALIDATION.json'))
 view=gh('release','view',TAG,'--json','assets',check=False)
 if view.returncode:
  gh('release','create',TAG,'--target',os.environ['RELEASE_COMMIT'],'--title','달핏 2.1.1 · 빌드 49','--notes-file',str(BASE/'RELEASE_NOTES.md'),'--latest');view=gh('release','view',TAG,'--json','assets')
 existing={a['name'] for a in json.loads(view.stdout)['assets']}
 for p in assets:
  if p.name in existing:
   folder=work/'existing';folder.mkdir(exist_ok=True);gh('release','download',TAG,'--pattern',p.name,'--dir',str(folder));assert digest((folder/p.name).read_bytes())==digest(p.read_bytes()),'Existing asset differs; refusing overwrite'
  else:gh('release','upload',TAG,str(p))
 print('Verified release',TAG)
 for item in CONFIG['assets']:print(item['name'],item['sha256'])
