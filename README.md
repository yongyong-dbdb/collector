# toss-chart-collector

Toss Securities Open API와 Yahoo Finance에서 시세 데이터를 수집해 PostgreSQL에 저장하는 Kubernetes용 Collector입니다.

## v1.6.0

- Toss 공식 Open API (`https://openapi.tossinvest.com`) 사용
- OAuth2 `client_credentials` 액세스 토큰 자동 발급 및 메모리 캐시
- 토큰 만료 또는 HTTP 401 발생 시 1회 자동 재발급
- `symbol_master.source_code`를 공식 Toss 심볼로 사용
- Yahoo Finance 수집 유지
- Kubernetes Secret 기반 자격증명 주입
- Stock Info 하루 1회 UPSERT
- 보유 계좌의 종목을 하루 1회 `symbol_master`에 자동 동기화
- 자동 추가 종목을 전량 매도하면 수집 비활성화, 수동 등록 종목은 유지
- 읽기 전용 API 허용목록 적용: 계좌·보유종목·종목정보·캔들만 허용하며 주문 API는 차단
- Toss 1분봉 누락 구간 자동 복구
  - 종목별 DB 마지막 Candle Time을 복구 anchor로 사용
  - 평상시에는 기존 `recent_candle_count`만 조회
  - 최근 페이지가 anchor에 닿지 않으면 `nextBefore` 기반으로 최대 200봉씩 과거 페이지 조회
  - `before`가 inclusive인 공식 API 동작에 맞춰 페이지 경계 중복 제거
  - anchor까지 도달한 후 한 번에 UPSERT하여 복구 도중 장애가 발생해도 DB의 최신 시각만 먼저 이동하지 않도록 보호
  - 반복 cursor, 빈 중간 페이지, anchor 도달 전 API history 종료를 오류로 처리하여 불완전 복구 방지

## 디렉터리

```text
collectors/     Toss 및 Yahoo Collector
k8s/            ConfigMap과 Deployment
sql/            전체 테이블, 뷰, 마이그레이션 SQL
tests/          Collector 회귀 테스트
config.py       환경변수 설정
database.py     PostgreSQL 연결
http_client.py  HTTP 재시도 처리
toss_auth.py    Toss OAuth2 토큰 관리
repository.py   데이터 조회 및 저장
main.py         Collector 실행 진입점
```

## 필수 Secret

실제 자격증명은 저장소에 커밋하지 않습니다.

```powershell
kubectl create secret generic toss-openapi-secret -n postgres --from-literal=client-id="$env:TOSS_OPENAPI_CLIENT_ID" --from-literal=client-secret="$env:TOSS_OPENAPI_CLIENT_SECRET"
```

Deployment는 다음 키를 환경변수로 주입합니다.

```text
client-id     -> TOSS_OPENAPI_CLIENT_ID
client-secret -> TOSS_OPENAPI_CLIENT_SECRET
```

## 검증

```powershell
python -m unittest discover -s tests -v
python -m py_compile .\collectors\toss.py .\repository.py .\http_client.py
```

## Docker

```powershell
docker build --no-cache -t yongyongvvv/toss-chart-collector:v1.6.0 -t yongyongvvv/toss-chart-collector:latest .
docker push yongyongvvv/toss-chart-collector:v1.6.0
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
kubectl logs -n postgres deployment/toss-chart-collector --follow
```

정상 수집 로그에는 `backfill_pages`와 `recovered`가 함께 출력됩니다. 장시간 중단 후 누락 복구가 발생하면 `backfill_pages`가 1 이상, `recovered`가 1 이상으로 기록됩니다.

## SQL

`sql/`에는 신규 환경 구성에 필요한 전체 테이블·뷰 SQL과 기존 환경 갱신용 마이그레이션이 포함됩니다. `v1.6.0`의 누락 구간 자동 복구는 기존 `toss_chart_candle` 테이블을 그대로 사용하므로 별도 DB 마이그레이션이 필요하지 않습니다.
