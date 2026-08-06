# toss-chart-collector

Toss Securities Open API와 Yahoo Finance에서 시세 데이터를 수집해 PostgreSQL에 저장하는 Kubernetes용 Collector입니다.

## v1.5.0

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

## 디렉터리

```text
collectors/     Toss 및 Yahoo Collector
k8s/            ConfigMap과 Deployment
sql/            전체 테이블, 뷰, 마이그레이션 SQL
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

## Docker

```powershell
docker build --no-cache -t yongyongvvv/toss-chart-collector:v1.5.0 -t yongyongvvv/toss-chart-collector:latest .
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

## SQL

`sql/`에는 신규 환경 구성에 필요한 전체 테이블·뷰 SQL과 기존 환경 갱신용 마이그레이션이 포함됩니다.
