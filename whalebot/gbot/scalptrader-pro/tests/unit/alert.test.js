const { sendSMS, formatSMS } = require('../../src/services/alert');
const { execSync } = require('child_process');
const NEON = require('../../src/utils/colors'); // Import NEON directly
const config = require('../../src/config'); // Import config to mock

jest.mock('child_process');
jest.mock('../../src/config', () => ({
    SYMBOL: 'BTCUSDT',
    TIMEFRAME: '3',
    PHONE_NUMBER: '1234567890'
}));


describe('Alert Service', () => {
    afterEach(() => {
        jest.clearAllMocks();
    });

    describe('formatSMS', () => {
        it('should format a LONG signal SMS correctly', () => {
            const signal = {
                direction: 'LONG',
                entry: '100',
                tp: '110',
                sl: '90',
                confidence: 'High',
                reasoning: 'Test reasoning'
            };
            const expectedSMS = `${config.SYMBOL.replace("USDT","")} ${config.TIMEFRAME}m LONG
Entry: 100
TP: 110 | SL: 90
Conf: High
AI: Test reasoning`;
            expect(formatSMS(signal)).toBe(expectedSMS);
        });

        it('should truncate a long reasoning', () => {
            const signal = {
                direction: 'SHORT',
                entry: '200',
                tp: '190',
                sl: '210',
                confidence: 'Medium',
                reasoning: 'This is a very long reasoning that should definitely be truncated because it exceeds the maximum length.'
            };
            const formatted = formatSMS(signal);
            expect(formatted).toContain('...');
            expect(formatted.length).toBeLessThan(160);
        });
    });

    describe('sendSMS', () => {
        it('should call execSync with the correct command', () => {
            const message = 'Test SMS message';
            sendSMS(message);
            expect(execSync).toHaveBeenCalledWith(`termux-sms-send -n "${config.PHONE_NUMBER}" "${message}"`, { stdio: 'ignore' });
        });

        it('should handle errors from execSync gracefully', () => {
            execSync.mockImplementation(() => {
                throw new Error('Test error');
            });
            const consoleLogSpy = jest.spyOn(console, 'log').mockImplementation();
            sendSMS('message');
            expect(consoleLogSpy).toHaveBeenCalledWith(NEON.RED("SMS failed"));
            consoleLogSpy.mockRestore();
        });
    });
});