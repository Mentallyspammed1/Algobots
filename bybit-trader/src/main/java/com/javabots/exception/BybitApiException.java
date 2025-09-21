package com.javabots.exception;

public class BybitApiException extends RuntimeException {
    private final int retCode;
    private final String retMsg;

    public BybitApiException(int retCode, String retMsg) {
        super("Bybit API Error: " + retMsg + " (Code: " + retCode + ")");
        this.retCode = retCode;
        this.retMsg = retMsg;
    }

    public BybitApiException(String message, int retCode, String retMsg) {
        super(message + " Bybit API Error: " + retMsg + " (Code: " + retCode + ")");
        this.retCode = retCode;
        this.retMsg = retMsg;
    }

    public int getRetCode() {
        return retCode;
    }

    public String getRetMsg() {
        return retMsg;
    }
}