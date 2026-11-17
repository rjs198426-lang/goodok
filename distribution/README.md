# 배포 파일 보관 기준

현재 앱: **달핏 2.2.0 · 빌드 56**

- [APK와 소스 다운로드](https://github.com/rjs198426-lang/goodok/releases/tag/dalfit-v2.2.0-build56)
- [현재 버전 검증 자료](dalfit-2.2.0/README.md)
- [이전 배포 목록](https://github.com/rjs198426-lang/goodok/releases)

현재 `publish_dalfit.py`와 배포 작업이 참조하는 `dalfit-2.2.0/`를 유지합니다. 해당 버전의 `RELEASE.json`에 기재된 모든 패치 조각·설명·검증 파일이 필요합니다.

현재 버전의 원본 파일은 `dalfit-v2.1.6-build55` **GitHub Releases 자산**에서 다운로드합니다. 이전 버전의 `distribution/` 폴더가 필요하다는 뜻은 아닙니다. 원본 APK·소스 ZIP은 현재 배포의 의존성이므로 Releases에서 삭제하면 안 됩니다.

다음 버전 배포가 성공하고 공개 APK·소스·체크섬을 확인한 뒤, 이전 버전 재조립 파일을 정리할 수 있습니다. 먼저 현재 배포 설정·실행 스크립트·테스트의 참조를 확인하세요. 운영 SQLite·앱 피드·자동 조사 보고서는 배포 임시 파일이 아닙니다.
