package com.javabots;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import okio.ByteString;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.concurrent.TimeUnit;

public class BybitWebSocketClient {

    private static final String PUBLIC_WS_URL = "wss://stream-testnet.bybit.com/v5/public/linear"; // Testnet public linear
    // For mainnet: private static final String PUBLIC_WS_URL = "wss://stream.bybit.com/v5/public/linear";

    private OkHttpClient client;
    private WebSocket webSocket;
    private ObjectMapper objectMapper;

    public BybitWebSocketClient() {
        this.client = new OkHttpClient.Builder()
                .readTimeout(0, TimeUnit.MILLISECONDS) // Disable read timeout for WebSockets
                .pingInterval(30, TimeUnit.SECONDS) // Send pings to keep connection alive
                .build();
        this.objectMapper = new ObjectMapper();
    }

    public void connect() {
        Request request = new Request.Builder().url(PUBLIC_WS_URL).build();
        webSocket = client.newWebSocket(request, new BybitWebSocketListener());
        System.out.println("Attempting to connect to Bybit Public WebSocket: " + PUBLIC_WS_URL);
    }

    public void subscribe(String topic) {
        if (webSocket != null) {
            String subscribeMessage = String.format("{\"op\":\"subscribe\",\"args\":[\"%s\"]}", topic);
            webSocket.send(subscribeMessage);
            System.out.println("Subscribed to topic: " + topic);
        } else {
            System.err.println("WebSocket not connected. Cannot subscribe to topic: " + topic);
        }
    }

    public void disconnect() {
        if (webSocket != null) {
            webSocket.close(1000, "Client initiated disconnect");
            System.out.println("Disconnected from Bybit Public WebSocket.");
        }
        client.dispatcher().executorService().shutdown();
    }

    private class BybitWebSocketListener extends WebSocketListener {
        @Override
        public void onOpen(WebSocket webSocket, Response response) {
            System.out.println("WebSocket connection opened successfully.");
            // You can subscribe to topics here immediately after connection
            // For example: subscribe("kline.1.BTCUSDT");
        }

        @Override
        public void onMessage(WebSocket webSocket, String text) {
            try {
                JsonNode rootNode = objectMapper.readTree(text);
                String op = rootNode.path("op").asText();

                if ("subscribe".equals(op)) {
                    System.out.println("Subscription response: " + text);
                } else if ("pong".equals(op)) {
                    // Handle pong response if needed, usually just indicates connection is alive
                } else if (rootNode.has("topic")) {
                    String topic = rootNode.path("topic").asText();
                    System.out.println("Received message for topic: " + topic);
                    // Process kline data
                    if (topic.startsWith("kline")) {
                        JsonNode data = rootNode.path("data");
                        if (data.isArray()) {
                            for (JsonNode klineNode : data) {
                                String symbol = klineNode.path("symbol").asText();
                                String interval = klineNode.path("interval").asText();
                                long start = klineNode.path("start").asLong();
                                double open = klineNode.path("open").asDouble();
                                double high = klineNode.path("high").asDouble();
                                double low = klineNode.path("low").asDouble();
                                double close = klineNode.path("close").asDouble();
                                double volume = klineNode.path("volume").asDouble();
                                boolean confirm = klineNode.path("confirm").asBoolean();

                                System.out.printf("  KLine: %s %s - O:%.2f H:%.2f L:%.2f C:%.2f V:%.2f Confirm:%b%n",
                                        symbol, interval, open, high, low, close, volume, confirm);
                            }
                        }
                    }
                } else {
                    System.out.println("Received unknown message: " + text);
                }
            } catch (Exception e) {
                System.err.println("Error parsing WebSocket message: " + e.getMessage());
                e.printStackTrace();
            }
        }

        @Override
        public void onMessage(WebSocket webSocket, ByteString bytes) {
            System.out.println("Received bytes: " + bytes.hex());
        }

        @Override
        public void onClosing(WebSocket webSocket, int code, String reason) {
            System.out.println("WebSocket closing: " + code + " / " + reason);
        }

        @Override
        public void onClosed(WebSocket webSocket, int code, String reason) {
            System.out.println("WebSocket closed: " + code + " / " + reason);
        }

        @Override
        public void onFailure(WebSocket webSocket, Throwable t, Response response) {
            System.err.println("WebSocket failure: " + t.getMessage());
            t.printStackTrace();
            if (response != null) {
                System.err.println("Failure response: " + response.code() + " / " + response.message());
            } else {
                System.err.println("Failure response was null.");
            }
            // Implement reconnection logic here
        }
    }
}
