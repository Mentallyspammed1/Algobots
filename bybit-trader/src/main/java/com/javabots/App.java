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
            TimeUnit.SECONDS.sleep(30); // Listen for 30 seconds
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            System.err.println("WebSocket listening interrupted.");
        } finally {
            wsClient.disconnect();
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
                    } else {
                        System.err.println("Response Body was null.");
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