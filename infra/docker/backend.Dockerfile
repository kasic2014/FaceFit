FROM maven:3.9.11-eclipse-temurin-21-alpine AS build

WORKDIR /workspace/backend
COPY backend/pom.xml ./
RUN mvn -B -ntp -DskipTests dependency:go-offline
COPY backend/src ./src
RUN mvn -B -ntp -DskipTests package

FROM eclipse-temurin:21-jre-alpine AS runtime

RUN addgroup -S facefit \
    && adduser -S -G facefit facefit

WORKDIR /app
COPY --from=build --chown=facefit:facefit \
    /workspace/backend/target/*.jar /app/app.jar

USER facefit
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=6 \
    CMD wget -q -O - http://127.0.0.1:8080/actuator/health >/dev/null || exit 1

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
