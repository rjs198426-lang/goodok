"""Reconstruct audited, signed release bytes. Signing material never leaves the build workspace."""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile
import bsdiff4
BASE=Path('distribution/dalfit-2.1.0')
TAG='dalfit-v2.1.0-build48'
OLD_TAG='dalfit-v2.0.2-build47'
APK='dalfit-2.1.0-build48-release.apk'
SOURCE='dalfit-android-source-2.1.0-build48.zip'
APK_SHA='1e006c6e4dcca6cf00bff2bfc10c0179a37190457dce7dcf726544eda56bcd18'
SOURCE_SHA='68fc87134cda3f3f20a6316975883b230848b1bee4c7937fe8d67cc0532eacef'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def gh(*args,check=True):return subprocess.run(['gh',*args],check=check,text=True,capture_output=True)
def restore(work,old_name,old_sha,patch,new_name,new_sha,size):
 gh('release','download',OLD_TAG,'--pattern',old_name,'--dir',str(work))
 old=work/old_name
 assert digest(old)==old_sha,'Base artifact checksum mismatch'
 target=work/new_name
 target.write_bytes(bsdiff4.patch(old.read_bytes(),patch))
 assert target.stat().st_size==size and digest(target)==new_sha,'Restored artifact checksum mismatch'
 return target
with tempfile.TemporaryDirectory() as temp:
 work=Path(temp)
 patch=b''.join((BASE/f'build48.bsdiff.part{n:03d}').read_bytes() for n in range(1,6))
 assert len(patch)==2689995 and hashlib.sha256(patch).hexdigest()=='f55c2286e526a70ebc46ac65497fed15c3bbb31ab334fbf4511abb7db7b9dfca'
 target=restore(work,'dalfit-2.0.2-build47-release.apk','ff5c0ec4e396cacc08fcc16feb0323fa5bbe6baf1cc31c97be5fd6bafe094b66',patch,APK,APK_SHA,48306028)
 source_patch=(BASE/'source48.bsdiff').read_bytes()
 assert len(source_patch)==94175 and hashlib.sha256(source_patch).hexdigest()=='08111e10c605f0630a4599120cb6dee433c92e56ab17ebefe0278ff8b2d9a527'
 source=restore(work,'dalfit-android-source-2.0.2-build47.zip','14467468f0bbe5474fa35850b791d74da5ed4814a056287c7cc305a2449d1b8d',source_patch,SOURCE,SOURCE_SHA,2431553)
 checksums=work/'SHA256SUMS.txt';checksums.write_text(APK_SHA+'  '+APK+'\n'+SOURCE_SHA+'  '+SOURCE+'\n')
 view=gh('release','view',TAG,'--json','assets',check=False)
 if view.returncode:
  gh('release','create',TAG,'--target',os.environ['RELEASE_COMMIT'],'--title','달핏 2.1.0 · 빌드 48','--notes-file',str(BASE/'RELEASE_NOTES.md'),'--latest')
  view=gh('release','view',TAG,'--json','assets')
 assets={a['name'] for a in json.loads(view.stdout)['assets']}
 for p in (target,checksums,source,BASE/'RESEARCH_REPORT.md',BASE/'VALIDATION.json'):
  if p.name in assets:
   downloaded=work/'existing';downloaded.mkdir(exist_ok=True)
   gh('release','download',TAG,'--pattern',p.name,'--dir',str(downloaded))
   assert digest(downloaded/p.name)==digest(p),'Existing release asset differs; refusing overwrite'
  else:gh('release','upload',TAG,str(p))
 print('Verified APK SHA-256:',APK_SHA)
 print('https://github.com/'+os.environ['GH_REPO']+'/releases/download/'+TAG+'/'+APK)
