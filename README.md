# 달핏 · 월간 비용과 카드피킹

**[2.2.0 · 빌드 56 APK 다운로드](https://github.com/rjs198426-lang/goodok/releases/download/dalfit-v2.2.0-build56/dalfit-2.2.0-build56-release.apk)**

[최신 배포 페이지](https://github.com/rjs198426-lang/goodok/releases/latest) · [Android 소스 ZIP](https://github.com/rjs198426-lang/goodok/releases/download/dalfit-v2.2.0-build56/dalfit-android-source-2.2.0-build56.zip) · [카드피킹 사용·계산 기준](distribution/dalfit-2.2.0/CARD_PICKING_NOTES.md)

기존 앱에 업데이트 설치하면 기록이 유지됩니다. 월간 비용에서 구독·고정비·취향비를 구분하고, 해당 월의 비용을 날짜별로 확인합니다. 카드피킹은 직접 입력한 카드사 이용·보유·혜택 이력과 행사별 기간을 기준으로 확인 예정일을 계산합니다. 계산 결과가 실제 행사 참여나 캐시백 지급을 확정하지는 않습니다.

## 자동 조사와 앱 데이터

GitHub Actions가 앱과 별도로 혜택·서비스·요금·분류를 조사하고 공식 출처와 대조합니다. 개인의 비용이나 카드피킹 기록은 이 저장소로 전송하지 않습니다.

- [자동 조사 보고서](backend/data/research-report.md)와 [앱용 JSON](backend/data/feed.json)에 실제 확인 시각·조건·출처·실패 원인·다음 조사 상태를 기록합니다.
- `backend/data/benefits.sqlite`는 조사 이력과 검증 대기열을 보관하는 운영 데이터베이스입니다.
- 매시 17분 UTC에 수집하고, 한국시간 매일 01시에도 실행합니다. GitHub 상황에 따라 예약 실행이 지연될 수 있습니다.
- 종료된 혜택과 72시간 넘게 재확인하지 못한 혜택은 공개 대상에서 제외합니다. 재확인과 신규 발굴은 따로 집계합니다.
- 가격은 공식 표시 통화와 약정·지역·세금·기능 근거를 유지합니다. 서로 다른 통화를 임의 환산해 절감액을 만들지 않습니다.
- Google/Naver 공식 검색 API는 저장소 Secrets에 설정한 경우 사용합니다. 미설정 시 공개 검색·RSS 등 기존 경로를 사용하며, 검색 결과만으로 혜택을 확정하지 않습니다.
- [조회·재시도 기준](backend/PIPELINE_V4.md) · [혜택 갱신 개선](backend/BENEFITS_REFRESH_V5.md)

## 저장소 구성

| 위치 | 용도 |
| --- | --- |
| `backend/` | 조사 코드·설정·테스트와 운영 데이터 |
| `distribution/dalfit-2.2.0/` | 현재 버전 재게시용 패치와 검증 자료 |
| `distribution/publish_dalfit.py` | 패치 복원·해시·APK 자산 검증 후 게시 |
| `.github/workflows/` | 자동 조사와 기존 앱 배포 작업 |

Android 전체 소스와 설치파일은 [Releases](https://github.com/rjs198426-lang/goodok/releases)에 보관합니다. 이전 버전 다운로드도 Releases에서 확인할 수 있습니다.

## 용량 관리

배포가 끝난 이전 버전의 재조립 조각·중복 소스 ZIP·배포용 복제 문서는 기본 브랜치에서 정리하고, 현재 배포 작업이 사용하는 파일과 운영 데이터는 유지합니다. 현재 배포의 `baseTag`는 이전 버전의 **Releases 자산**을 사용합니다.

[2026-11-17 정리 내역과 검증 범위](docs/repository-cleanup-2026-11-17.md) · [배포 파일 보관 기준](distribution/README.md)

일반 파일 삭제 후에도 과거 Git 이력에는 파일이 남습니다. 기본 브랜치의 파일 용량·체크아웃 크기 감소와 GitHub 저장소 전체 표시 용량은 구분해야 합니다.
