package com.facefit.backend.interview.application;

import com.facefit.backend.interview.integration.PortResult;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

@Component
public class ExternalCallExecutor {

    private final ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();

    public <T> PortResult<T> call(
            Callable<PortResult<T>> operation,
            Duration timeout
    ) {
        Future<PortResult<T>> future = executor.submit(operation);
        try {
            PortResult<T> result = future.get(timeout.toMillis(), TimeUnit.MILLISECONDS);
            return result == null
                    ? PortResult.permanentFailure("EMPTY_PORT_RESULT")
                    : result;
        } catch (TimeoutException exception) {
            future.cancel(true);
            return PortResult.retryableFailure("EXTERNAL_CALL_TIMEOUT");
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            future.cancel(true);
            return PortResult.retryableFailure("EXTERNAL_CALL_INTERRUPTED");
        } catch (ExecutionException exception) {
            return PortResult.retryableFailure("EXTERNAL_CALL_FAILED");
        }
    }

    @PreDestroy
    void shutdown() {
        executor.shutdownNow();
    }
}
