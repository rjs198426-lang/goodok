"""Machine-readable and readable result reports generated with each collection."""
import json
from pathlib import Path

def cell(value):return str(value or '미확인').replace('|','／').replace('\n',' ')
def write_report(db,feed,directory):
 directory=Path(directory);research=feed['research'];metrics=research['metrics'];latest=research.get('latestRun',{});outcomes=metrics['factCheckOutcomes']
 report={'generatedAt':feed['generatedAt'],'pipelineVersion':3,'publishedOffers':len(feed['offers']),'catalogueServices':len(feed['catalog']),'newServicesCumulative':metrics['newServiceCount'],'newServicesThisRun':latest.get('newServices',0),'candidatesRetained':research['candidateCount'],'candidatesIncludingRejected':research['rawCandidateCount'],'factCheckOutcomes':outcomes,'latestRun':latest,'offers':feed['offers'],'newServices':[s for s in feed['catalog'] if s.get('origin')=='discovered'],'tasteSuggestions':feed.get('tasteSuggestions',[]),'providerHealth':research.get('providerHealth',[])}
 (directory/'research-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 confirmed=sum(outcomes.get(s,0) for s in ('official_verified','corroborated'))
 lines=['# 달핏 백그라운드 조사 결과',f'기준 UTC: {feed["generatedAt"]} · 파이프라인 3','',f'- 공개 중인 혜택: {len(feed["offers"])}개 (기존 혜택 재확인은 신규 발굴과 별도)',f'- 외부 후보 대조 확정 기록: {confirmed}개 / 대조 기록 {sum(outcomes.values())}개',f'- 서비스 목록: {len(feed["catalog"])}개 · 신규 편입 누적 {metrics["newServiceCount"]}개 · 이번 실행 신규 {latest.get("newServices",0)}개',f'- 유효 후보 URL: {research["candidateCount"]}개 · 제외 이력 포함 {research["rawCandidateCount"]}개',f'- 요금제: 검증 {metrics["verifiedPlanCount"]}개 / 미확정 {metrics["candidatePlanCount"]}개',f'- 공식 기간 확인 취향 정보: {len(feed.get("tasteSuggestions",[]))}개','','## 현재 혜택','| 서비스 | 혜택 | 조건 | 최초 발견 | 마지막 확인 | 출처 |','| --- | --- | --- | --- | --- | --- |']
 for o in feed['offers']:lines.append('| '+' | '.join(map(cell,[o['service'],o['benefit'],o['conditions'],o.get('firstSeen'),o['verifiedAt'],o['source']]))+' |')
 lines+=['','## 기능 검증 범위',json.dumps(metrics.get('featureCoverage',{}),ensure_ascii=False),f"비교 가능한 원화 정상 플랜: {metrics.get('comparableKRWPlans',0)}개"]
 lines+=['','## 신규 서비스','서비스 식별과 가격·지역·기능 검증은 서로 다른 단계입니다.','| 이름 | 상태 | 용도 | 확인된 공식 주소 |','| --- | --- | --- | --- |']
 for s in report['newServices']:lines.append('| '+' | '.join(map(cell,[s['name'],s['status'],', '.join(s.get('purposes',[])),s['officialUrl']]))+' |')
 lines+=['','공식 검색 API 연결: '+', '.join(name+(' 연결됨' if ready else ' 설정 필요') for name,ready in research.get('searchApiConnections',{}).items())]
 lines+=['','## 출처 접근 및 재시도','| 출처 | 최신 상태 | 다음 재시도 UTC |','| --- | --- | --- |']
 for p in report['providerHealth']:lines.append('| '+' | '.join(map(cell,[p['name'],p['status'],p.get('nextCheckAt') or '제한 없음']))+' |')
 lines+=['','작업 성공은 모든 사이트의 조회 성공을 의미하지 않습니다. 검색 결과와 할인 주장은 공식 정보로 대조하기 전까지 확정하지 않습니다. 차단된 사이트의 제한을 우회하지 않습니다. 취향 정보의 표시 가격은 실제 지출로 자동 등록하지 않습니다.','']
 (directory/'research-report.md').write_text('\n'.join(lines))
