# toss-chart-collector

Toss Securities Open API, Toss Invest WTS 뉴스, Yahoo Finance에서 금융 데이터를 수집해 PostgreSQL에 저장하는 Kubernetes용 Collector입니다.

## v1.7.1

- v1.7.0 뉴스 수집 복원 기능 유지
- Toss WTS 뉴스 상세 응답의 다국어 구조(`result.availableLanguages`, `result.kr`) 처리 추가
- 한국어 상세 응답에서 본문, 감성, 출처, 기자, 관련 종목/기업 코드, 원문 링크, 생성·수정 시각 정상 파싱
- 상세 본문이 비어 있는 경우 정상 수집으로 저장하지 않고 오류 처리
- v1.7.0에서 잘못 저장된 `content=''` 상세 행을 재수집 대상으로 자동 인식
- 정상 재수집 시 기존 빈 `market_news_detail` 행을 `ON CONFLICT DO UPDATE`로 복구
- v1.6.0 Toss 1분봉 누락 구간 자동 복구 기능 유지
- Toss 공식 Open API (`https://openapi.tossinvest.com`) 기반 Candle, 계좌 보유종목, Stock Info 수집 유지
- OAuth2 `client_credentials` 액세스 토큰 자동 발급 및 메모리 캐시 유지
- Yahoo Finance 지표 수집 유지

### 뉴스 목록

- `POST /api/v1/dashboard/wts/news`
- 기본 범위 `ALL_HIGHLIGHT`
- 서버 한도에 맞춰 Cycle당 최대 50건
- `newsId`, 제목, 요약, 언론사, 유형, 관련 종목, 국가, 생성시각 UPSERT
- `relatedStocks`는 `stockCode`, `stockName`, `market`만 보존

### 뉴스 상세

- `GET /api/v2/news/{newsId}`
- 신규 상세 행 또는 `content`가 비어 있는 기존 상세 행만 조회
- 기본 Cycle당 최대 20건
- 실제 응답 구조 예시: `result.availableLanguages=["kr"]`, 본문 객체는 `result.kr`
- 본문, 요약문, 감성, 출처, 기자, 관련 종목/기업 코드, 원문 링크 저장
- 타임존 없는 WTS 시각은 Asia/Seoul 기준으로 저장
- `[[기사 핵심 요약]]`, 이메일, `(끝)`, 저작권/무단전재 문구 정제
- 본문 파싱 결과가 비어 있으면 DB 저장 차단

뉴스 목록과 상세 결과는 `collector_run_history`에 `TOSS_NEWS / LIST`, `TOSS_NEWS / DETAIL`로 분리 기록합니다. 상세 API 일부 실패 시 목록 적재와 성공한 상세 적재는 유지합니다.

> Toss WTS 뉴스 API는 Toss Securities 공식 Open API가 아니라 웹 서비스 내부 API입니다. 내부 API의 응답 구조가 변경되면 Collector 수정이 필요할 수 있습니다.

## 디렉터리

```text
collectors/
  toss.py          Toss 공식 Candle Collector
  reference.py     계좌 보유종목/Stock Info 동기화
  yahoo.py         Yahoo Finance 지표 Collector
  news.py          Toss WTS 뉴스 목록/상세 Collector
k8s/               ConfigMap과 Deployment
sql/               전체 테이블, 뷰, 마이그레이션 SQL
tests/             Collector 회귀 테스트
config.py          환경변수 설정
database.py        PostgreSQL 연결
http_client.py     공식 API/Yahoo HTTP 재시도 처리
toss_auth.py       Toss 공식 Open API OAuth2 토큰 관리
wts_client.py      Toss WTS 익명 웹 세션과 뉴스 HTTP 처리
repository.py      Candle/Reference 데이터 조회 및 저장
news_repository.py 뉴스 목록/상세 조회 및 Batch UPSERT
main.py            Collector 실행 진입점
```

## 뉴스 설정

`k8s/configmap.yaml` 기본값:

```text
ENABLE_TOSS_NEWS=true
TOSS_WTS_WEB_BASE_URL=https://www.tossinvest.com
TOSS_WTS_INFO_BASE_URL=https://wts-info-api.tossinvest.com
TOSS_NEWS_SCOPE=ALL_HIGHLIGHT
TOSS_NEWS_LIMIT=50
TOSS_NEWS_DETAIL_ENABLED=true
TOSS_NEWS_DETAIL_MAX_PER_CYCLE=20
```

뉴스 목록은 WTS 피드 페이지를 먼저 조회해 익명 Session/Cookie와 XSRF Token을 준비한 뒤 WTS Info API를 호출합니다. HTTP 401/403 발생 시 Session을 한 번 재초기화하고, 429/5xx는 기존 Retry/Backoff 정책에 따라 재시도합니다.

## 필수 Secret

공식 Toss Open API 자격증명은 저장소에 커밋하지 않습니다.

```powershell
kubectl create secret generic toss-openapi-secret -n postgres --from-literal=client-id="$env:TOSS_OPENAPI_CLIENT_ID" --from-literal=client-secret="$env:TOSS_OPENAPI_CLIENT_SECRET"
```

Deployment는 다음 키를 환경변수로 주입합니다.

```text
client-id     -> TOSS_OPENAPI_CLIENT_ID
client-secret -> TOSS_OPENAPI_CLIENT_SECRET
```

WTS 뉴스는 별도 계정 자격증명을 GitHub나 Kubernetes Secret에 저장하지 않고 익명 웹 Session을 사용합니다.

## 검증

```powershell
python -m unittest discover -s tests -v
python -m py_compile .\collectors\toss.py .\collectors\news.py .\repository.py .\news_repository.py .\http_client.py .\wts_client.py .\config.py .\main.py
```

`v1.7.1` 기준 회귀 테스트는 기존 Candle 5건 + News 5건으로 총 10건입니다.

## Docker

```powershell
docker build --no-cache -t yongyongvvv/toss-chart-collector:v1.7.1 -t yongyongvvv/toss-chart-collector:latest .
docker push yongyongvvv/toss-chart-collector:v1.7.1
docker push yongyongvvv/toss-chart-collector:latest
```

## Kubernetes 배포

```powershell
kubectl apply -f .\k8s\configmap.yaml
kubectl apply -f .\k8s\deployment.yaml
kubectl rollout status deployment/toss-chart-collector -n postgres
```

## 로그 확인

```powershell
kubectl logs -n postgres deployment/toss-chart-collector --tail=200
kubectl logs -n postgres deployment/toss-chart-collector --follow
```

뉴스 정상 수집 로그 예시:

```text
[TOSS:NEWS:LIST] status=SUCCESS fetched=50 upserted=50
[TOSS:NEWS:DETAIL] status=SUCCESS requested=20 fetched=20 upserted=20 failed=0
```

## SQL

기존 `sql/02_create_market_news.sql`의 `market_news`, `market_news_detail`을 그대로 사용하므로 v1.7.1 수정에는 별도 DB 마이그레이션이 필요하지 않습니다.

확인 쿼리:

```sql
SELECT COUNT(*) AS news_count, MAX(created_at) AS latest_news
FROM public.market_news;

SELECT COUNT(*) AS detail_count, MAX(collected_at) AS latest_detail
FROM public.market_news_detail;

SELECT
    news_id,
    language,
    source_name,
    sentiment,
    length(content) AS content_length,
    created_at
FROM public.market_news_detail
ORDER BY created_at DESC NULLS LAST
LIMIT 20;

SELECT
    n.news_id,
    n.title,
    n.created_at
FROM public.market_news AS n
LEFT JOIN public.market_news_detail AS d
       ON d.news_id = n.news_id
WHERE d.news_id IS NULL
   OR NULLIF(BTRIM(d.content), '') IS NULL
ORDER BY n.created_at DESC;
```
