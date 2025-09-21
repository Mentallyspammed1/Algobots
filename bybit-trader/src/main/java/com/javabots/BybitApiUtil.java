package com.javabots;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;
import java.util.concurrent.TimeUnit;

public class BybitApiUtil {

    private static final String HMAC_SHA256 = "HmacSHA256";
    private static final long RECV_WINDOW = 5000; // 5 seconds

    /**
     * Generates the HMAC SHA256 signature for a Bybit API request.
     *
     * @param apiKey The Bybit API Key.
     * @param apiSecret The Bybit API Secret.
     * @param timestamp The current timestamp in milliseconds.
     * @param recvWindow The recvWindow value.
     * @param paramStr The parameter string (query string for GET, JSON body for POST).
     * @return The generated signature.
     * @throws NoSuchAlgorithmException If HMAC_SHA256 algorithm is not available.
     * @throws InvalidKeyException If the API secret is invalid.
     */
    public static String generateSignature(String apiKey, String apiSecret, long timestamp, long recvWindow, String paramStr)
            throws NoSuchAlgorithmException, InvalidKeyException {

        String payload = timestamp + apiKey + recvWindow + paramStr;

        Mac sha256_HMAC = Mac.getInstance(HMAC_SHA256);
        SecretKeySpec secret_key = new SecretKeySpec(apiSecret.getBytes(StandardCharsets.UTF_8), HMAC_SHA256);
        sha256_HMAC.init(secret_key);

        byte[] hash = sha256_HMAC.doFinal(payload.getBytes(StandardCharsets.UTF_8));
        return bytesToHex(hash);
    }

    /**
     * Converts a byte array to a hexadecimal string.
     *
     * @param bytes The byte array to convert.
     * @return The hexadecimal string.
     */
    private static String bytesToHex(byte[] bytes) {
        StringBuilder result = new StringBuilder();
        for (byte b : bytes) {
            result.append(String.format("%02x", b));
        }
        return result.toString();
    }

    /**
     * Gets the current timestamp in milliseconds.
     *
     * @return The current timestamp.
     */
    public static long getTimestamp() {
        return System.currentTimeMillis();
    }

    /**
     * Gets the default recvWindow.
     *
     * @return The recvWindow value.
     */
    public static long getRecvWindow() {
        return RECV_WINDOW;
    }
}
