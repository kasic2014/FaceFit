package com.facefit.backend.interview.integration.http;

import java.io.IOException;
import java.io.InputStream;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

@FunctionalInterface
interface AiHttpTransport {

    HttpResponse<InputStream> send(HttpRequest request)
            throws IOException, InterruptedException;
}
