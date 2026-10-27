"""Publish already signed APK bytes; no signing material is stored in this repo."""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile,zipfile

BASE=Path('distribution/dalfit-2.0.1')
TAG='dalfit-v2.0.1-build46'
APK='dalfit-2.0.1-build46-release.apk'
APK_SHA='aab21fbacf6f4adfe9694339d2f10f5fa200ab19ed5ab89258b1eed82a8329ec'
ZIP_SHA='86b4da254be7c5b81e31fe3f83bda2ee1bc37ab255fa388b75cf0f3a4842252e'
parts=[BASE/f'build46.zip.part{n:03}' for n in range(1,4)]
assert all(p.is_file() for p in parts),'Missing distribution part'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def gh(*args,check=True):return subprocess.run(['gh',*args],check=check,text=True,capture_output=True)

with tempfile.TemporaryDirectory() as work:
 work=Path(work);archive=work/'verified.zip'
 with archive.open('wb') as out:
  for p in parts:out.write(p.read_bytes())
 assert archive.stat().st_size==23646866 and digest(archive)==ZIP_SHA,'Distribution checksum mismatch'
 target=work/APK
 with zipfile.ZipFile(archive) as z:
  assert set(z.namelist())=={APK,'SHA256SUMS.txt'}
  assert z.getinfo(APK).file_size==48303788
  target.write_bytes(z.read(APK))
 assert target.stat().st_size==48303788 and digest(target)==APK_SHA,'APK checksum mismatch'
 checksums=work/'SHA256SUMS.txt';checksums.write_text(APK_SHA+'  '+APK+'\n')
 view=gh('release','view',TAG,'--json','assets',check=False)
 if view.returncode:
  gh('release','create',TAG,'--target',os.environ['RELEASE_COMMIT'],'--title','달핏 2.0.1 · 빌드 46 · 보안 검증 대기','--notes-file',str(BASE/'RELEASE_NOTES.md'),'--prerelease')
  view=gh('release','view',TAG,'--json','assets')
 assets={a['name'] for a in json.loads(view.stdout)['assets']}
 source=BASE/'dalfit-android-source-2.0.1-build46.zip'
 assert digest(source)=='704b4efd75e27b4c20b733077a7895751591c726134356df31a7a8b679737f1a','Source checksum mismatch'
 for p in (target,checksums,source,BASE/'SECURITY_REVIEW.md',BASE/'VALIDATION.json',BASE/'APPEAL.txt'):
  if p.name in assets:
   downloaded=work/'existing';downloaded.mkdir(exist_ok=True)
   gh('release','download',TAG,'--pattern',p.name,'--dir',str(downloaded))
   assert digest(downloaded/p.name)==digest(p),'Existing release asset differs; refusing to overwrite'
  else:gh('release','upload',TAG,str(p))
 print('Verified APK SHA-256:',APK_SHA)
 print('https://github.com/'+os.environ['GH_REPO']+'/releases/download/'+TAG+'/'+APK)

# Preserve the old release but put the reported block in front of its download.
old=gh('api','repos/'+os.environ['GH_REPO']+'/releases/tags/dalfit-v2.0.0-build45')
old=json.loads(old.stdout)
warning='> ⚠️ Play 프로텍트 유해/위험 앱 차단 보고가 있습니다. 2.0.0 설치를 권장하지 않습니다. 원인 및 오탐 여부는 미확정입니다. 보호 기능을 끄지 마세요. [2.0.1 권한 축소 수정본·검증 대기](https://github.com/rjs198426-lang/goodok/releases/tag/dalfit-v2.0.1-build46)\n\n'
body=old.get('body') or ''
if 'Play 프로텍트 유해/위험 앱 차단 보고' not in body:body=warning+body
gh('api','--method','PATCH','repos/'+os.environ['GH_REPO']+'/releases/'+str(old['id']),'-F','prerelease=true','-f','make_latest=false','-f','body='+body)
