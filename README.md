# 구독노트 할인 데이터

GitHub Actions가 매시간 공식 구독 사이트를 조회·검증하고 SQLite 데이터베이스와 앱용 JSON을 갱신합니다. 개인의 구독 기록은 이 저장소에 저장하지 않습니다.

- 실행: 매시 17분 UTC cron, 수동 실행, 수집 코드 변경 시. GitHub 상황에 따라 예약 실행이 지연될 수 있습니다.
- 수집: 14개 공식 사이트. 유독·티빙·웨이브는 공식 이벤트 상세 링크도 탐색합니다. 직접 확인 가능한 혜택만 공개하며, 미확인·차단·스크립트 전용 페이지는 상태로 기록합니다.
- 데이터베이스: `backend/data/benefits.sqlite`에 수집 실행, 출처별 조사 내역, 할인 이력, 비교 프로필을 저장합니다.
- 앱용 데이터: `backend/data/feed.json`. 출처·혜택 조건·확인 시각·수집 상태·비교 프로필을 제공합니다.
- 신선도: 공식 종료일이 지난 혜택 및 72시간 넘게 재확인되지 않은 혜택은 제외합니다. 실패한 사이트의 기존 확인 시각을 새로 갱신하지 않습니다.
- 비용: 기본 Python 표준 라이브러리와 GitHub Actions를 사용합니다. 일반 웹 검색 API나 유료 AI API는 사용하지 않습니다. GitHub Actions 이용 한도와 정책이 적용됩니다.
- 가격 비교: 앱에 기록한 실제 지출과 공식 정상 플랜을 구분합니다. 검증된 원화 월간 요금과 기능 증거를 사용하며 다른 통화는 자동 환산하지 않습니다. 사용자에게 대안 가격 입력을 요구하지 않습니다.

앱이 인증 없이 읽으려면 이 데이터 저장소 또는 JSON 배포 주소를 공개로 제공해야 합니다. APK에 GitHub 토큰을 넣지 마세요.

```sh
python -m unittest discover -s backend/tests -v
python backend/collector.py
```

`Collect subscription benefits hourly` 작업의 Run workflow로 첫 수집을 시작할 수 있습니다. 모든 출처 연결이 실패하면 작업은 실패로 보고하고 이전 정상 자료의 실제 확인일을 유지합니다.

## Research pipeline v3 · 2026-10-27

- 검색 메뉴·지도·사전·광고·SNS·APK 안내를 후보에서 제외합니다. 기존 불필요한 후보도 삭제 대신 제외 상태로 보관합니다. URL 추적 매개변수를 제거하고 긴 서비스 별칭을 우선 연결합니다.
- Google News RSS는 매체 홈페이지로 바꾸지 않고 실제 기사 링크를 보존합니다. 공개 기사·공식 사이트의 링크를 따라가며 원문 조건을 확인합니다.
- 검증할 서비스를 찾지 못한 후보는 별도 대기 상태와 다음 시각을 저장합니다. 이 후보들이 뒤의 검증 가능한 항목을 막지 않습니다. 실패·미확인·확인 완료 모두 재확인 시각을 갖습니다.
- 검색 공급자의 차단·연결 실패에는 지수 간격 재시도를 적용합니다. CAPTCHA·로그인 제한을 우회하지 않으며, 접근 실패를 할인 없음으로 기록하지 않습니다.
- 같은 공식 페이지의 일반·가족·대상 기기·학생·결제 수단별 체험과 날짜가 명시된 여러 행사를 각각 추출합니다. 종료일이 없는 체험을 한정 행사라고 표시하지 않습니다.
- 사업자 식별, 정기 결제 가격, 약정, 지역, 유료 기능 범위를 별도로 저장합니다. 조건이 부족한 가격은 candidate로 유지합니다. 무료 부가 상품 설명으로 전체 유료 구독을 분류하지 않도록 복합 용도와 근거를 저장합니다.
- 취향 조사는 구독과 별도 검색·대기열·테이블로 실행합니다. 지정된 공공 문화 기관의 공식 행사 제목·유효 기간을 확인한 정보만 tasteSuggestions에 내보냅니다. 가격을 모르면 금액을 만들지 않으며 앱 실제 지출로 자동 입력하지 않습니다.
- 매 실행마다 backend/data/research-report.md 및 research-report.json을 갱신합니다. 기존 혜택 재확인과 신규 편입, 검증 보류와 확정을 분리합니다. 출처 실패·재시도·제외 후보·가격 검증 지표를 피드에도 제공합니다.

## Existing collection rules

The scheduled job runs without the Android app. Runs query Google, Naver and Bing public search pages, Google News RSS, and a rotating selection of eight deal/community sites, subject to provider retry times. Failures, blocks, empty or irrelevant results and deferred attempts are recorded explicitly. RSS retains article links and publisher identity separately. No captcha or access restriction is bypassed.

- The existing 53 services seed a persistent catalogue. Ten catalogue entries are revisited per run, using a durable cursor rather than a fixed 14-page ceiling.
- Discovery URLs, referral URLs, claims and official fact checks are stored separately. Third-party text alone cannot enter the verified offers feed.
- New providers require a referring discovery source, matching first-party structured organization identity, and an explicit recurring structured price. Brand/domain collisions, lifetime licences, unclear billing intervals and unsupported prices remain pending.
- Structured monthly/yearly prices and supported source-specific normal prices are recorded with currency, period, region, introductory eligibility, verification time and evidence. Trial prices do not become normal comparison prices.
- The feed exports `catalog`, `plans` and `research` as well as existing offers. Unknown conditions are preserved as unknown; an absent value does not mean a missing feature.
- Search/crawl budgets bound each run; the persistent queues and cursors expand coverage over successive hourly runs. Search engines may deny automated access, and JavaScript-only sites may remain unverified. The run's actual statuses are exposed in `research.providers`.

Automatic comparison policy: the Android app has no manual alternative-price field. Alternatives require a normal, recently verified KRW monthly price, a known one-month commitment, an identified baseline and evidence that known baseline capabilities are preserved. There must also be a lower price or a proven feature improvement; extra cost is shown explicitly. Missing feature evidence is unknown, not false. Introductory prices, stale observations, mismatched currency/region and unknown commitments do not qualify. When nothing qualifies, the app displays no substitute.

The candidate table keeps catalogue processing state separately from fact-check state. A failed or already-known candidate cannot permanently occupy the front of the expansion queue; failures can be retried after one day while other pending providers continue to be investigated.

## Optional official search API connections

Google and Naver public-page/RSS research remains available without API keys. When automated HTML access is blocked, an official API connection can be configured using GitHub Actions repository secrets:

- `GOOGLE_SEARCH_API_KEY` and `GOOGLE_SEARCH_ENGINE_ID`: an enabled Google Custom Search JSON API project/engine.
- `NAVER_CLIENT_ID` and `NAVER_CLIENT_SECRET`: an authorized Naver Search API application.

No credentials have been provisioned by this change. Usage/quota or billing follows the account owner's provider configuration. Credentials stay in request headers and are never put in the APK, feed, published URLs or logs. Missing/failed API connections retain the existing public search/RSS path, retry times and official evidence requirements. API responses are search leads, never verified benefits by themselves.
