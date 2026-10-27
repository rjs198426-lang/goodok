# 달핏 2.0.1 · 빌드 46 — 보안 검증 대기

**2.0.0에서 Play 프로텍트의 유해/위험 앱 설치 차단이 보고됐습니다. 이번 수정본의 Google 판정 해제 여부는 아직 확인되지 않았습니다. 보호 기능을 끄거나 차단을 무시하여 설치하지 마세요.**

- 다른 앱의 알림을 읽는 서비스와 접근 설정·출처 선택을 제거했습니다. 차단 원인이라는 증거는 아직 없습니다.
- 직접 선택한 이미지·공유 입력과 기존 검토 내역, 거래·예산·백업, 달핏 자체의 결제 알림은 유지합니다.
- 기존 설치 호환을 위한 개발용 인증서는 유지했습니다. 서명 유효성을 Google의 안전 판정으로 설명하지 않습니다.
- 앱 단위49개·브라우저10개 묶음·release 빌드·lint 오류0개. 병합 매니페스트와 DEX에 알림 읽기 서비스가 없음을 확인했습니다. 실기기·Google 재검증은 남아 있습니다.

[보안 대응 및 검토 자료](https://github.com/rjs198426-lang/goodok/blob/main/distribution/dalfit-2.0.1/SECURITY_REVIEW.md) · [Google 공식 검토 요청](https://support.google.com/googleplay/android-developer/contact/protectappeals)

Assets에 수정 APK, 소스, 해시와 검토 자료를 포함합니다. 신규 서명이나 패키지 이름으로 판정을 우회하는 배포가 아닙니다. 기존 앱을 삭제하지 마세요.

APK SHA-256: `aab21fbacf6f4adfe9694339d2f10f5fa200ab19ed5ab89258b1eed82a8329ec`
