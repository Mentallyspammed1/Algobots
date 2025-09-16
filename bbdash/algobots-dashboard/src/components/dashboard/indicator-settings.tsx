'use client';

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { defaultIndicatorSettings, type IndicatorSettings } from '@/lib/indicators';
import { useForm, Controller, useFieldArray } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { IndicatorSettings as IndicatorSettingsSchema } from '@/lib/indicators';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';

interface IndicatorSettingsDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  settings: IndicatorSettings;
  onSettingsChange: (settings: IndicatorSettings) => void;
}

export function IndicatorSettingsDialog({ isOpen, onOpenChange, settings, onSettingsChange }: IndicatorSettingsDialogProps) {
    const form = useForm<IndicatorSettings>({
        resolver: zodResolver(IndicatorSettingsSchema),
        defaultValues: settings,
    });
    
    const onSubmit = (data: IndicatorSettings) => {
        onSettingsChange(data);
        onOpenChange(false);
    };

    const handleReset = () => {
        form.reset(defaultIndicatorSettings);
    }
    
    const renderNumberInput = (name: any, label: string) => (
        <FormField
            control={form.control}
            name={name}
            render={({ field }) => (
                <FormItem>
                    <div className="flex items-center justify-between">
                        <FormLabel>{label}</FormLabel>
                        <FormControl>
                            <Input 
                                type="number" 
                                className="w-24" 
                                {...field} 
                                onChange={e => field.onChange(parseInt(e.target.value, 10) || 0)}
                            />
                        </FormControl>
                    </div>
                    <FormMessage />
                </FormItem>
            )}
        />
    )

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Indicator Settings</DialogTitle>
          <DialogDescription>
            Customize the parameters for the technical indicators.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)}>
                <ScrollArea className="h-96 p-4">
                <div className="space-y-6">
                    <div>
                        <h4 className="font-semibold mb-2 text-lg">General</h4>
                        {renderNumberInput('sma.period', 'SMA Period')}
                    </div>
                    <div>
                        <h4 className="font-semibold mb-2 text-lg">Supertrend</h4>
                        {renderNumberInput('supertrendFast.atrPeriod', 'Fast ATR Period')}
                        {renderNumberInput('supertrendFast.multiplier', 'Fast Multiplier')}
                        {renderNumberInput('supertrendSlow.atrPeriod', 'Slow ATR Period')}
                        {renderNumberInput('supertrendSlow.multiplier', 'Slow Multiplier')}
                    </div>
                    <div>
                        <h4 className="font-semibold mb-2 text-lg">Oscillators</h4>
                        {renderNumberInput('rsi.period', 'RSI Period')}
                        {renderNumberInput('rsi.overbought', 'RSI Overbought')}
                        {renderNumberInput('rsi.oversold', 'RSI Oversold')}
                        {renderNumberInput('stochastic.period', 'Stochastic Period')}
                        {renderNumberInput('stochastic.slowing', 'Stochastic Slowing (D)')}
                        {renderNumberInput('stochastic.overbought', 'Stochastic Overbought')}
                        {renderNumberInput('stochastic.oversold', 'Stochastic Oversold')}
                        {renderNumberInput('williamsR.period', 'Williams %R Period')}
                        {renderNumberInput('williamsR.overbought', 'Williams %R Overbought')}
                        {renderNumberInput('williamsR.oversold', 'Williams %R Oversold')}
                         {renderNumberInput('cci.period', 'CCI Period')}
                        {renderNumberInput('cci.overbought', 'CCI Overbought')}
                        {renderNumberInput('cci.oversold', 'CCI Oversold')}
                         {renderNumberInput('roc.period', 'ROC Period')}
                         {renderNumberInput('mfi.period', 'MFI Period')}
                        {renderNumberInput('mfi.overbought', 'MFI Overbought')}
                        {renderNumberInput('mfi.oversold', 'MFI Oversold')}
                    </div>

                    <div>
                        <h4 className="font-semibold mb-2 text-lg">MACD</h4>
                        {renderNumberInput('macd.fast', 'Fast EMA')}
                        {renderNumberInput('macd.slow', 'Slow EMA')}
                        {renderNumberInput('macd.signal', 'Signal Line')}
                    </div>
                    <div>
                        <h4 className="font-semibold mb-2 text-lg">Bollinger Bands</h4>
                        {renderNumberInput('bollingerBands.period', 'Period')}
                        {renderNumberInput('bollingerBands.stdDev', 'Std. Deviations')}
                    </div>

                    <div>
                        <h4 className="font-semibold mb-2 text-lg">Other</h4>
                        {renderNumberInput('atr.period', 'ATR Period')}
                         {renderNumberInput('awesomeOscillator.fast', 'AO Fast Period')}
                        {renderNumberInput('awesomeOscillator.slow', 'AO Slow Period')}
                        {renderNumberInput('ichimokuCloud.tenkan', 'Ichimoku Tenkan-sen')}
                        {renderNumberInput('ichimokuCloud.kijun', 'Ichimoku Kijun-sen')}
                        {renderNumberInput('ichimokuCloud.senkou', 'Ichimoku Senkou Span B')}
                        {renderNumberInput('fisher.period', 'Fisher Period')}
                        {renderNumberInput('ehlers.period', 'Ehlers Period')}
                    </div>
                </div>
                </ScrollArea>
                <DialogFooter className="pt-4">
                    <Button type="button" variant="outline" onClick={handleReset}>Reset to Default</Button>
                    <Button type="submit">Save Changes</Button>
                </DialogFooter>
            </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
