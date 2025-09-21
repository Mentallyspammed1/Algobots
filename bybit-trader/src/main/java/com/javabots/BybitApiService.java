package com.javabots;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import okhttp3.*;

import java.io.IOException;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;
import java.util.Objects;

public class BybitApiService {

    private static final String BASE_URL = "https://api-testnet.bybit.com"; // Use testnet
    private static final MediaType JSON = MediaType.get("application/json; charset=utf-8");

    private final OkHttpClient client;
    private final String apiKey;
    private final String apiSecret;
    private final ObjectMapper objectMapper;

    public BybitApiService(OkHttpClient client, String apiKey, String apiSecret) {
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
     * Fetches open positions for a given category and symbol.
     *
     * @param category The product category (e.g., "linear").
     * @param symbol The trading pair (e.g., "BTCUSDT").
     * @return JsonNode response from Bybit API.
     * @throws IOException If an I/O error occurs.
     * @throws NoSuchAlgorithmException If HMAC_SHA256 algorithm is not available.
     * @throws InvalidKeyException If the API secret is invalid.
     */
    public JsonNode getOpenPositions(String category, String symbol)
            throws IOException, NoSuchAlgorithmException, InvalidKeyException {

        String path = "/v5/position/list";
        HttpUrl.Builder urlBuilder = HttpUrl.parse(BASE_URL + path).newBuilder();
        urlBuilder.addQueryParameter("category", category);
        if (symbol != null && !symbol.isEmpty()) {
            urlBuilder.addQueryParameter("symbol", symbol);
        }

        // For GET requests, paramStr is the sorted query string without the base URL
        String paramStr = "category=" + category;
        if (symbol != null && !symbol.isEmpty()) {
            paramStr += "&symbol=" + symbol;
        }

        return executeGetRequest(urlBuilder.build(), path, paramStr);
    }

    /**
     * Fetches transaction logs (asset transfers) for the account.
     *
     * @param accountType The account type (e.g., "UNIFIED").
     * @param currency The currency (e.g., "USDT").
     * @param startTime Start time in milliseconds. (Optional)
     * @param endTime End time in milliseconds. (Optional)
     * @param limit Number of records to return. (Optional)
     * @return JsonNode response from Bybit API.
     * @throws IOException If an I/O error occurs.
     * @throws NoSuchAlgorithmException If HMAC_SHA256 algorithm is not available.
     * @throws InvalidKeyException If the API secret is invalid.
     */
    public JsonNode getTransactionLog(String accountType, String currency, Long startTime, Long endTime, Integer limit)
            throws IOException, NoSuchAlgorithmException, InvalidKeyException {

        String path = "/v5/asset/transfer/query";
        HttpUrl.Builder urlBuilder = HttpUrl.parse(BASE_URL + path).newBuilder();
        urlBuilder.addQueryParameter("accountType", accountType);
        if (currency != null && !currency.isEmpty()) {
            urlBuilder.addQueryParameter("coin", currency);
        }
        if (startTime != null) {
            urlBuilder.addQueryParameter("startTime", String.valueOf(startTime));
        }
        if (endTime != null) {
            urlBuilder.addQueryParameter("endTime", String.valueOf(endTime));
        }
        if (limit != null) {
            urlBuilder.addQueryParameter("limit", String.valueOf(limit));
        }

        // Build paramStr for signature
        StringBuilder paramStrBuilder = new StringBuilder();
        paramStrBuilder.append("accountType=").append(accountType);
        if (currency != null && !currency.isEmpty()) {
            paramStrBuilder.append("&coin=").append(currency);
        }
        if (startTime != null) {
            paramStrBuilder.append("&startTime=").append(startTime); // Append as string
        }
        if (endTime != null) {
            paramStrBuilder.append("&endTime=").append(endTime); // Append as string
        }
        if (limit != null) {
            paramStrBuilder.append("&limit=").append(limit); // Append as string
        }

        return executeGetRequest(urlBuilder.build(), path, paramStrBuilder.toString());
    }


    /**
     * Executes a POST request to the Bybit API with authentication.
     *
     * @param path The API endpoint path (e.g., "/v5/order/create").
     * @param requestBodyJson The JSON string for the request body.
     * @return JsonNode response from Bybit API. (Includes retCode and retMsg)
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

    /**
     * Executes a GET request to the Bybit API with authentication.
     *
     * @param url The full HttpUrl object including query parameters.
     * @param path The API endpoint path (e.g., "/v5/position/list").
     * @param paramStr The sorted query string for signature generation.
     * @return JsonNode response from Bybit API. (Includes retCode and retMsg)
     * @throws IOException If an I/O error occurs.
     * @throws NoSuchAlgorithmException If HMAC_SHA256 algorithm is not available.
     * @throws InvalidKeyException If the API secret is invalid.
     */
    private JsonNode executeGetRequest(HttpUrl url, String path, String paramStr)
            throws IOException, NoSuchAlgorithmException, InvalidKeyException {

        long timestamp = BybitApiUtil.getTimestamp();
        long recvWindow = BybitApiUtil.getRecvWindow();

        // For GET requests, the signature payload is timestamp + apiKey + recvWindow + paramStr
        String signature = BybitApiUtil.generateSignature(apiKey, apiSecret, timestamp, recvWindow, paramStr);

        Request request = new Request.Builder()
                .url(url)
                .get()
                .addHeader("X-BAPI-API-KEY", apiKey)
                .addHeader("X-BAPI-TIMESTAMP", String.valueOf(timestamp))
                .addHeader("X-BAPI-RECV-WINDOW", String.valueOf(recvWindow))
                .addHeader("X-BAPI-SIGN", signature)
                .build();

        System.out.println("Sending GET request to: " + url);

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
