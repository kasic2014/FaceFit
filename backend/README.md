# FACE-FIT Backend

Java 21과 Spring Boot 3.5 기반의 FACE-FIT 백엔드입니다. 인증은 Supabase Auth가 발급한 Access Token을 검증하는 OAuth2 Resource Server 방식입니다.

## 로컬 준비

1. `.env.example`을 참고해 실행 환경변수를 설정합니다.
2. Java 21을 사용합니다.
3. `mvnw.cmd test` 또는 `./mvnw test`로 테스트합니다.
4. `mvnw.cmd spring-boot:run` 또는 `./mvnw spring-boot:run`으로 실행합니다.

애플리케이션은 `.env` 파일을 자동으로 읽지 않습니다. IDE 실행 설정, 운영체제 환경변수 또는 별도의 안전한 비밀 관리 수단으로 값을 주입해야 합니다.

## 인증 확인

Supabase Access Token을 다음과 같이 전달합니다.

```http
GET /api/v1/auth/me
Authorization: Bearer {SUPABASE_ACCESS_TOKEN}
```

Spring Boot는 OAuth Redirect·Callback, 자체 JWT 또는 Refresh Token을 발급하지 않습니다.
