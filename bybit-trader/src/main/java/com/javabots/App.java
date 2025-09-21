package com.javabots;

import io.github.cdimascio.dotenv.Dotenv;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.HttpUrl;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public class App {

    private static final String BASE_URL = "https://api-testnet.bybit.com"; // Use testnet for initial testing
    // For mainnet, change to: private static final String BASE_URL = "https://api.bybit.com";

    public static void main(String[] args) {
        // Load environment variables from .env file
        Dotenv dotenv = Dotenv.load();
        String apiKey = dotenv.get("BYBIT_API_KEY");
        String apiSecret = dotenv.get("BYBIT_API_SECRET");

        if (apiKey == null || apiSecret == null) {
            System.err.println("BYBIT_API_KEY or BYBIT_API_SECRET not found in .env file.");
            return;
        }

        OkHttpClient client = new OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS)
                .writeTimeout(10, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .build();

        // --- Fetching Server Time (Public Endpoint - No Auth) ---
        System.out.println("\n--- Fetching Server Time (Public Endpoint) ---");
        fetchServerTime(client);

        // --- Authenticated API Service ---
        BybitApiService apiService = new BybitApiService(client, apiKey, apiSecret);

        // --- Fetching Wallet Balance (Private Endpoint - Requires Auth) ---
        System.out.println("\n--- Fetching Wallet Balance (Private Endpoint) ---");
        fetchWalletBalance(client, apiKey, apiSecret);

        // --- Real-time Market Data (WebSocket) ---
        System.out.println("\n--- Connecting to Bybit Public WebSocket for Market Data ---");
        BybitWebSocketClient wsClient = new BybitWebSocketClient();
        wsClient.connect();

        // Give some time for the WebSocket to connect and receive data
        try {
            TimeUnit.SECONDS.sleep(5); // Wait 5 seconds for connection to establish
            wsClient.subscribe("kline.1.BTCUSDT"); // Subscribe to 1-minute kline for BTCUSDT
            TimeUnit.SECONDS.sleep(10); // Listen for 10 seconds
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            System.err.println("WebSocket listening interrupted.");
        }

        // --- Order Management System (OMS) ---
        System.out.println("\n--- Demonstrating Order Management System (OMS) ---");
        String orderLinkId = "my-test-order-" + UUID.randomUUID().toString().substring(0, 8); // Unique ID for the order

        try {
            // 1. Place a Limit Buy Order
            System.out.println("\nAttempting to place a LIMIT BUY order for BTCUSDT...");
            JsonNode placeOrderResponse = apiService.placeOrder(
                    "linear",       // category
                    "BTCUSDT",      // symbol
                    "Buy",          // side
                    "Limit",        // orderType
                    "0.001",        // qty (adjust based on your balance and min order size)
                    "20000",        // price (set a price far from current market to avoid immediate fill)
                    false,          // reduceOnly
                    false,          // closeOnTrigger
                    "GTC",          // timeInForce (Good-Till-Cancelled)
                    orderLinkId     // custom order link ID
            );
            System.out.println("Place Order Response: " + placeOrderResponse.toPrettyString());

            String placedOrderId = placeOrderResponse.path("result").path("orderId").asText();
            if (!placedOrderId.isEmpty()) {
                System.out.println("Order placed successfully with ID: " + placedOrderId);
                System.out.println("Waiting 5 seconds before attempting to cancel...");
                TimeUnit.SECONDS.sleep(5);

                // 2. Cancel the Order
                System.out.println("\nAttempting to cancel order with Order ID: " + placedOrderId);
                JsonNode cancelOrderResponse = apiService.cancelOrder(
                        "linear",
                        "BTCUSDT",
                        placedOrderId,
                        null // Using orderId, so orderLinkId is null
                );
                System.out.println("Cancel Order Response: " + cancelOrderResponse.toPrettyString());
                if (cancelOrderResponse.path("retCode").asInt() == 0) {
                    System.out.println("Order cancelled successfully.");
                } else {
                    System.err.println("Failed to cancel order: " + cancelOrderResponse.path("retMsg").asText());
                }
            } else {
                System.err.println("Failed to place order. No orderId returned.");
            }

        } catch (IOException | NoSuchAlgorithmException | InvalidKeyException | InterruptedException e) {
            System.err.println("An error occurred during OMS operations: " + e.getMessage());
            e.printStackTrace();
        }

        // --- Account & Wallet Management Module ---
        System.out.println("\n--- Demonstrating Account & Wallet Management Module ---");
        try {
            // 1. Get Open Positions
            System.out.println("\nAttempting to fetch Open Positions for BTCUSDT...");
            JsonNode positionsResponse = apiService.getOpenPositions("linear", "BTCUSDT");
            System.out.println("Open Positions Response: " + positionsResponse.toPrettyString());

            // 2. Get Transaction Log (last 7 days for USDT)
            System.out.println("\nAttempting to fetch Transaction Log for USDT (last 7 days)...");
            long endTime = System.currentTimeMillis();
            long startTime = endTime - TimeUnit.DAYS.toMillis(7); // Last 7 days
            JsonNode transactionLogResponse = apiService.getTransactionLog(
                    "UNIFIED",
                    "USDT",
                    startTime,
                    endTime,
                    10 // limit to 10 records
            );
            System.out.println("Transaction Log Response: " + transactionLogResponse.toPrettyString());

        } catch (IOException | NoSuchAlgorithmException | InvalidKeyException e) {
            System.err.println("An error occurred during Account & Wallet Management operations: " + e.getMessage());
            e.printStackTrace();
        } finally {
            wsClient.disconnect(); // Ensure WebSocket is disconnected
        }
    }

    private static void fetchServerTime(OkHttpClient client) {
        String serverTimeUrl = BASE_URL + "/v5/market/time";
        Request request = new Request.Builder().url(serverTimeUrl).get().build();

        try (Response response = client.newCall(request).execute()) {
            if (response.isSuccessful() && response.body() != null) {
                String responseBody = response.body().string();
                ObjectMapper objectMapper = new ObjectMapper();
                JsonNode rootNode = objectMapper.readTree(responseBody);
                String serverTime = rootNode.path("result").path("timeNano").asText();
                System.out.println("Successfully fetched Bybit Server Time (nanoseconds): " + serverTime);
            } else {
                System.err.println("Failed to fetch server time. HTTP Code: " + response.code() + ", Message: " + response.message());
                if (response.body() != null) {
                    System.err.println("Response Body: " + response.body().string());
                }
            }
        } catch (IOException e) {
            System.err.println("An error occurred while connecting to Bybit API for server time: " + e.getMessage());
            e.printStackTrace();
        }
    }

    private static void fetchWalletBalance(OkHttpClient client, String apiKey, String apiSecret) {
        String walletBalancePath = "/v5/account/wallet-balance";
        String accountType = "UNIFIED"; // Required for V5 API

        long timestamp = BybitApiUtil.getTimestamp();
        long recvWindow = BybitApiUtil.getRecvWindow();

        String paramStr = "accountType=" + accountType;

        try {
            String signature = BybitApiUtil.generateSignature(apiKey, apiSecret, timestamp, recvWindow, paramStr);

            HttpUrl url = HttpUrl.parse(BASE_URL + walletBalancePath).newBuilder()
                    .addQueryParameter("accountType", accountType)
                    .build();

            Request request = new Request.Builder()
                    .url(url)
                    .get()
                    .addHeader("X-BAPI-API-KEY", apiKey)
                    .addHeader("X-BAPI-TIMESTAMP", String.valueOf(timestamp))
                    .addHeader("X-BAPI-RECV-WINDOW", String.valueOf(recvWindow))
                    .addHeader("X-BAPI-SIGN", signature)
                    .build();

            System.out.println("Attempting to fetch Wallet Balance from: " + url);

            try (Response response = client.newCall(request).execute()) {
                if (response.isSuccessful() && response.body() != null) {
                    String responseBody = response.body().string();
                    ObjectMapper objectMapper = new ObjectMapper();
                    JsonNode rootNode = objectMapper.readTree(responseBody);

                    System.out.println("Successfully fetched Wallet Balance:");
                    System.out.println(objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(rootNode));
                } else {
                    System.err.println("Failed to fetch wallet balance. HTTP Code: " + response.code() + ", Message: " + response.message());
                    if (response.body() != null) {
                        System.err.println("Response Body: " + response.body().string());
                    }
                }
            } catch (IOException e) {
                System.err.println("An error occurred while connecting to Bybit API for wallet balance: " + e.getMessage());
                e.printStackTrace();
            }

        } catch (NoSuchAlgorithmException | InvalidKeyException e) {
            System.err.println("Error generating signature: " + e.getMessage());
            e.printStackTrace();
        }
    }
}