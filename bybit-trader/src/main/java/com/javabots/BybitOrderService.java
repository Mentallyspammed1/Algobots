package com.javabots;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import okhttp3.*;

import java.io.IOException;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;
import java.util.Objects;

public class BybitOrderService {

    private static final String BASE_URL = "https://api-testnet.bybit.com"; // Use testnet
    private static final MediaType JSON = MediaType.get("application/json; charset=utf-8");

    private final OkHttpClient client;
    private final String apiKey;
    private final String apiSecret;
    private final ObjectMapper objectMapper;

    public BybitOrderService(OkHttpClient client, String apiKey, String apiSecret) {
        this.client = client;
        this.apiKey = apiKey;
        this.apiSecret = apiSecret;
        this.objectMapper = new ObjectMapper();
    }

    /**
     * Places a new order on Bybit.
     *
     * @param category The product category (e.g., "linear", "inverse", "spot").
     * @param symbol The trading pair (e.g., "BTCUSDT").
     * @param side The order side ("Buy" or "Sell").
     * @param orderType The order type ("Limit" or "Market").
     * @param qty The quantity of the order.
     * @param price The price for Limit orders (null for Market orders).
     * @param reduceOnly Whether the order is reduce-only.
     * @param closeOnTrigger Whether to close position on trigger.
     * @param timeInForce Time in force policy (e.g., "GTC", "IOC", "FOK").
     * @param orderLinkId A custom unique order ID.
     * @return JsonNode response from Bybit API.
     * @throws IOException If an I/O error occurs.
     * @throws NoSuchAlgorithmException If HMAC_SHA256 algorithm is not available.
     * @throws InvalidKeyException If the API secret is invalid.
     */
    public JsonNode placeOrder(String category, String symbol, String side, String orderType,
                               String qty, String price, Boolean reduceOnly, Boolean closeOnTrigger,
                               String timeInForce, String orderLinkId)
            throws IOException, NoSuchAlgorithmException, InvalidKeyException {

        String path = "/v5/order/create";
        ObjectNode requestBody = objectMapper.createObjectNode();
        requestBody.put("category", category);
        requestBody.put("symbol", symbol);
        requestBody.put("side", side);
        requestBody.put("orderType", orderType);
        requestBody.put("qty", qty);
        if (price != null) {
            requestBody.put("price", price);
        }
        if (reduceOnly != null) {
            requestBody.put("reduceOnly", reduceOnly);
        }
        if (closeOnTrigger != null) {
            requestBody.put("closeOnTrigger", closeOnTrigger);
        }
        if (timeInForce != null) {
            requestBody.put("timeInForce", timeInForce);
        }
        if (orderLinkId != null) {
            requestBody.put("orderLinkId", orderLinkId);
        }

        return executePostRequest(path, requestBody.toString());
    }

    /**
     * Cancels an existing order on Bybit.
     *
     * @param category The product category.
     * @param symbol The trading pair.
     * @param orderId The order ID.
     * @param orderLinkId The custom unique order ID.
     * @return JsonNode response from Bybit API.
     * @throws IOException If an I/O error occurs.
     * @throws NoSuchAlgorithmException If HMAC_SHA256 algorithm is not available.
     * @throws InvalidKeyException If the API secret is invalid.
     */
    public JsonNode cancelOrder(String category, String symbol, String orderId, String orderLinkId)
            throws IOException, NoSuchAlgorithmException, InvalidKeyException {

        String path = "/v5/order/cancel";
        ObjectNode requestBody = objectMapper.createObjectNode();
        requestBody.put("category", category);
        requestBody.put("symbol", symbol);
        if (orderId != null) {
            requestBody.put("orderId", orderId);
        }
        if (orderLinkId != null) {
            requestBody.put("orderLinkId", orderLinkId);
        }

        return executePostRequest(path, requestBody.toString());
    }

    /**
     * Executes a POST request to the Bybit API with authentication.
     *
     * @param path The API endpoint path (e.g., "/v5/order/create").
     * @param requestBodyJson The JSON string for the request body.
     * @return JsonNode response from Bybit API.
     * @throws IOException If an I/O error occurs.
     * @throws NoSuchAlgorithmException If HMAC_SHA256 algorithm is not available.
     * @throws InvalidKeyException If the API secret is invalid.
     */
    private JsonNode executePostRequest(String path, String requestBodyJson)
            throws IOException, NoSuchAlgorithmException, InvalidKeyException {

        long timestamp = BybitApiUtil.getTimestamp();
        long recvWindow = BybitApiUtil.getRecvWindow();

        // For POST requests, the signature payload is timestamp + apiKey + recvWindow + requestBodyJson
        String signature = BybitApiUtil.generateSignature(apiKey, apiSecret, timestamp, recvWindow, requestBodyJson);

        RequestBody body = RequestBody.create(requestBodyJson, JSON);

        Request request = new Request.Builder()
                .url(BASE_URL + path)
                .post(body)
                .addHeader("X-BAPI-API-KEY", apiKey)
                .addHeader("X-BAPI-TIMESTAMP", String.valueOf(timestamp))
                .addHeader("X-BAPI-RECV-WINDOW", String.valueOf(recvWindow))
                .addHeader("X-BAPI-SIGN", signature)
                .addHeader("Content-Type", "application/json")
                .build();

        System.out.println("Sending POST request to: " + BASE_URL + path);
        System.out.println("Request Body: " + requestBodyJson);

        try (Response response = client.newCall(request).execute()) {
            String responseBody = Objects.requireNonNull(response.body()).string();
            if (response.isSuccessful()) {
                System.out.println("Successful response from " + path);
            } else {
                System.err.println("Failed response from " + path + ". HTTP Code: " + response.code() + ", Message: " + response.message());
            }
            return objectMapper.readTree(responseBody);
        }
    }
}
