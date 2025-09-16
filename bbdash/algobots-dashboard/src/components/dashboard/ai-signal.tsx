'use client';

import { useState, useCallback } from 'react';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Bot, Zap, TrendingUp, TrendingDown, CircleDot, Shield, BrainCircuit, AlertTriangle, Info, Clock, Gauge, FileDown, Settings, Eye, EyeOff, Scale } from 'lucide-react';
import { getAiTradingSignal } from '@/lib/actions';
import type { GenerateTradingSignalOutput as AiSignalResponse } from '@/ai/flows/generate-trading-signal';
import { Skeleton } from '@/components/ui/skeleton';
import { useToast } from '@/hooks/use-toast';
import { Badge } from '@/components/ui/badge';
import type { IndicatorSettings } from '@/lib/indicators';
import { Terminal } from '@/components/ui/terminal';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Collapsible, CollapsibleContent } from "@/components/ui/collapsible";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from '@/lib/utils';

interface AiSignalProps {
  symbol: string;
  timeframe: string;
  indicatorSettings: IndicatorSettings;
}

interface AdvancedSettings {
  riskProfile: 'conservative' | 'moderate' | 'aggressive';
  accountBalance?: number;
  maxRiskPercentage: number;
}

const getConfidenceVariant = (level: 'High' | 'Medium' | 'Low' | undefined) => {
  switch (level) {
    case 'High': return 'default';
    case 'Medium': return 'secondary';
    case 'Low': return 'outline';
    default: return 'outline';
  }
};

const getSignalColor = (signal: 'Buy' | 'Sell' | 'Hold' | undefined) => {
  switch(signal) {
    case 'Buy': return 'text-chart-2';
    case 'Sell': return 'text-chart-5';
    default: return 'text-muted-foreground';
  }
};

const getVolatilityColor = (level: 'Low' | 'Medium' | 'High' | 'Extreme' | undefined) => {
  switch(level) {
    case 'Low': return 'text-blue-500';
    case 'Medium': return 'text-yellow-500';
    case 'High': return 'text-orange-500';
    case 'Extreme': return 'text-red-500';
    default: return 'text-muted-foreground';
  }
};

export function AiSignal({ symbol, timeframe, indicatorSettings }: AiSignalProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [analysis, setAnalysis] = useState<AiSignalResponse | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  
  const [advancedSettings, setAdvancedSettings] = useState<AdvancedSettings>({
    riskProfile: 'moderate',
    maxRiskPercentage: 2,
  });
  const { toast } = useToast();

  const handleGenerateSignal = useCallback(async () => {
    setIsLoading(true);
    setAnalysis(null);
    const result = await getAiTradingSignal({
        symbol,
        timeframe,
        indicatorSettings,
        ...advancedSettings,
    });

    if (result.success && result.analysis) {
      setAnalysis(result.analysis);
      if (result.analysis.warnings?.length) {
        result.analysis.warnings.forEach(warning => {
          toast({
            title: 'Trading Warning',
            description: warning,
          });
        });
      }
    } else {
      toast({
        variant: 'destructive',
        title: 'Error Generating Signal',
        description: result.error || 'Failed to generate trading signal. Please try again.',
      });
    }
    setIsLoading(false);
  }, [symbol, timeframe, indicatorSettings, advancedSettings, toast]);

  const exportAnalysis = () => {
    if (!analysis) return;
    const dataStr = JSON.stringify(analysis, null, 2);
    const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
    const exportFileDefaultName = `signal-${symbol}-${new Date().toISOString()}.json`;
    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportFileDefaultName);
    linkElement.click();
  };

  const renderDetail = (
    icon: React.ReactNode,
    label: string,
    value: string | number | (string | number)[] | undefined,
    valueClass?: string,
    tooltip?: string,
    isCurrency = true,
    isUnits = false
  ) => {
    let displayValue = '-';
    if (value !== undefined && value !== null) {
      if (Array.isArray(value)) {
        displayValue = value.map(v => `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`).join(', ');
      } else if (typeof value === 'number' && !isNaN(value)) {
        if (isUnits) {
          displayValue = `${Number(value).toFixed(5)} units`;
        } else if (isCurrency) {
          displayValue = `$${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        } else {
          displayValue = `${Number(value).toFixed(2)}`;
        }
      } else if (typeof value === 'string') {
        displayValue = value;
      }
    }

    return (
        <TooltipProvider>
        <Tooltip>
            <TooltipTrigger asChild>
            <div className="flex items-start justify-between gap-4 hover:bg-accent/50 p-2 rounded-md transition-colors">
                <div className="flex items-center gap-2 text-muted-foreground shrink-0">
                {icon}
                <span className="text-sm">{label}</span>
                </div>
                <div className={cn("text-sm font-semibold text-right flex-grow", valueClass)}>
                {displayValue}
                </div>
            </div>
            </TooltipTrigger>
            {tooltip && (
            <TooltipContent>
                <p>{tooltip}</p>
            </TooltipContent>
            )}
        </Tooltip>
        </TooltipProvider>
    );
  }
  
  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bot className="h-5 w-5" />
              <CardTitle>AI Trading Intelligence</CardTitle>
              {analysis && (
                <Badge variant="outline" className="ml-2">
                  <Clock className="mr-1 h-3 w-3" />
                  {new Date(analysis.analysisTimestamp).toLocaleTimeString()}
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-2">
              {analysis && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button size="icon" variant="outline" onClick={exportAnalysis}>
                        <FileDown className="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>Export Analysis</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
              <Button onClick={() => setShowAdvanced(!showAdvanced)} variant="outline" size="icon" >
                <Settings className="h-4 w-4" />
              </Button>
              <Button onClick={handleGenerateSignal} disabled={isLoading}>
                <Zap className="mr-2 h-4 w-4" /> {isLoading ? 'Analyzing...' : 'Generate Signal'}
              </Button>
            </div>
          </div>
          <Collapsible open={showAdvanced} onOpenChange={setShowAdvanced}>
            <CollapsibleContent>
              <Card className="border-dashed">
                <CardContent className="grid grid-cols-2 md:grid-cols-3 gap-4 pt-6">
                  <div className="space-y-2">
                    <Label>Risk Profile</Label>
                    <Select value={advancedSettings.riskProfile} onValueChange={(value: any) => setAdvancedSettings({...advancedSettings, riskProfile: value}) } >
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="conservative">Conservative</SelectItem>
                        <SelectItem value="moderate">Moderate</SelectItem>
                        <SelectItem value="aggressive">Aggressive</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Max Risk %</Label>
                    <Input type="number" min="0.1" max="10" step="0.1" value={advancedSettings.maxRiskPercentage} onChange={(e) => setAdvancedSettings({ ...advancedSettings, maxRiskPercentage: parseFloat(e.target.value) }) } />
                  </div>
                  <div className="space-y-2">
                    <Label>Account Balance ($)</Label>
                    <Input type="number" placeholder="Optional" value={advancedSettings.accountBalance || ''} onChange={(e) => setAdvancedSettings({ ...advancedSettings, accountBalance: e.target.value ? parseFloat(e.target.value) : undefined }) } />
                  </div>
                </CardContent>
              </Card>
            </CollapsibleContent>
          </Collapsible>
        </div>
      </CardHeader>
      <CardContent className="pt-6">
        {isLoading && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[...Array(3)].map((_, i) => ( <Skeleton key={i} className="h-20" /> ))}
            </div>
            <Skeleton className="h-32" />
          </div>
        )}
        {!isLoading && !analysis && (
          <div className="text-center py-12">
            <Bot className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-lg font-semibold mb-2">Ready to Analyze</p>
            <p className="text-muted-foreground"> Click "Generate Signal" to receive AI-powered trading intelligence. </p>
          </div>
        )}
        {analysis && (
          <div className="space-y-6">
            <Card className={cn(
              "border-2",
              analysis.signal === 'Buy' && "border-chart-2/50 bg-chart-2/5",
              analysis.signal === 'Sell' && "border-chart-5/50 bg-chart-5/5",
              analysis.signal === 'Hold' && "border-yellow-500/50 bg-yellow-500/5"
            )}>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-4">
                    <div className={cn("text-4xl font-bold", getSignalColor(analysis.signal))}>
                      {analysis.signal}
                    </div>
                    <div className="space-y-1">
                      <Badge variant={getConfidenceVariant(analysis.confidenceLevel)}>
                        {analysis.confidenceLevel} Confidence
                      </Badge>
                      <div className="flex items-center gap-1">
                        <Gauge className="h-3 w-3" />
                        <span className="text-xs text-muted-foreground">
                          Signal Strength: {analysis.signalStrength}/100
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold">
                      ${analysis.currentPrice?.toLocaleString() || '0'}
                    </div>
                    <div className="text-xs text-muted-foreground">Current Price</div>
                  </div>
                </div>
                {analysis.signalStrength !== undefined && ( <Progress value={analysis.signalStrength} className="h-2" /> )}
              </CardContent>
            </Card>
            
            {analysis.warnings && analysis.warnings.length > 0 && (
              <Alert>
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Risk Warnings</AlertTitle>
                <AlertDescription>
                  <ul className="list-disc list-inside space-y-1">
                    {analysis.warnings.map((warning, index) => ( <li key={index} className="text-sm">{warning}</li> ))}
                  </ul>
                </AlertDescription>
              </Alert>
            )}

            <Tabs defaultValue="overview" className="w-full">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="technical">Technical</TabsTrigger>
                <TabsTrigger value="risk">Risk</TabsTrigger>
              </TabsList>
              
              <TabsContent value="overview" className="space-y-4 pt-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm">Entry & Exit</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {renderDetail(<CircleDot/>, "Entry Price", analysis.entryPrice, "", "Recommended entry point")}
                      {renderDetail(<TrendingUp className="text-chart-2"/>, `Take Profit`, analysis.takeProfit, "text-chart-2", `Target levels`)}
                      {renderDetail(<TrendingDown className="text-chart-5"/>, "Stop Loss", analysis.stopLoss, "text-chart-5", "Risk management stop")}
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm">Market Context</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      <div className="flex justify-between items-center text-sm"><span className="text-muted-foreground">Market Regime</span><Badge variant="outline">{analysis.marketRegime}</Badge></div>
                      <div className="flex justify-between items-center text-sm"><span className="text-muted-foreground">Volatility</span><span className={cn("font-semibold", getVolatilityColor(analysis.volatilityLevel))}>{analysis.volatilityLevel}</span></div>
                    </CardContent>
                  </Card>
                </div>
                <Card>
                  <CardHeader className="pb-3"><CardTitle className="text-sm flex items-center gap-2"><BrainCircuit className="h-4 w-4" /> AI Reasoning</CardTitle></CardHeader>
                  <CardContent>
                    {analysis.reasoning ? (
                        <Terminal text={analysis.reasoning} className="max-h-48" />
                    ) : (
                        <p className="text-sm text-muted-foreground p-4">No detailed reasoning available for this signal.</p>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="technical" className="space-y-4 pt-4">
                {analysis.keyLevels && (
                  <Card>
                    <CardHeader className="pb-3"><CardTitle className="text-sm">Key Price Levels</CardTitle></CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 gap-4">
                        <div><h4 className="text-sm font-semibold mb-2 text-chart-2">Support</h4><div className="space-y-1">{analysis.keyLevels.support.map((level, i) => (<div key={i} className="text-sm"> ${level.toLocaleString()} </div>))}</div></div>
                        <div><h4 className="text-sm font-semibold mb-2 text-chart-5">Resistance</h4><div className="space-y-1">{analysis.keyLevels.resistance.map((level, i) => (<div key={i} className="text-sm"> ${level.toLocaleString()} </div>))}</div></div>
                      </div>
                    </CardContent>
                  </Card>
                )}
                {analysis.patterns && analysis.patterns.length > 0 && (
                  <Card>
                    <CardHeader className="pb-3"><CardTitle className="text-sm">Detected Patterns</CardTitle></CardHeader>
                    <CardContent><div className="space-y-2">{analysis.patterns.map((p, i) => (<div key={i} className="flex items-center justify-between p-2 rounded-md bg-accent/10"><span className="text-sm font-medium">{p.name}</span><Badge variant="outline">{p.reliability}% Rel.</Badge></div>))}</div></CardContent>
                  </Card>
                )}
                {analysis.divergences && analysis.divergences.length > 0 && (
                  <Card>
                    <CardHeader className="pb-3"><CardTitle className="text-sm">Divergences</CardTitle></CardHeader>
                    <CardContent><div className="space-y-2">{analysis.divergences.map((d, i) => (<div key={i} className="flex items-center justify-between"><span className={cn("text-sm font-medium", d.type === 'Bullish' ? 'text-chart-2' : 'text-chart-5')}>{d.type} Divergence</span><div className="flex items-center gap-2"><Badge variant="outline">{d.indicator}</Badge></div></div>))}</div></CardContent>
                  </Card>
                )}
              </TabsContent>

              <TabsContent value="risk" className="space-y-4 pt-4">
                <Card>
                  <CardHeader className="pb-3"><CardTitle className="text-sm">Position & Risk</CardTitle></CardHeader>
                  <CardContent className="space-y-2">
                    {renderDetail(<Scale/>, "Position Size", analysis.positionSize, "", "Recommended units to buy/sell based on your account balance and risk profile.", false, true)}
                    {renderDetail(<Shield/>, "Max Loss", (analysis.positionSize && analysis.entryPrice && analysis.stopLoss) ? Math.abs(analysis.entryPrice - analysis.stopLoss) * analysis.positionSize : undefined, "text-red-500", "Maximum potential loss for this trade.")}
                    {renderDetail(<TrendingUp className="text-chart-2"/>, "Risk/Reward Ratio", analysis.riskRewardRatio, "", "Ratio of potential profit to potential loss.", false, false)}
                  </CardContent>
                </Card>
              </TabsContent>

            </Tabs>

             <Button variant="outline" className="w-full" onClick={() => setShowDetails(!showDetails)} >
                {showDetails ? <EyeOff className="mr-2 h-4 w-4" /> : <Eye className="mr-2 h-4 w-4" />}
                {showDetails ? 'Hide Raw Data' : 'Show Raw Data'}
            </Button>
            {showDetails && (
                <Card>
                <CardContent className="pt-6">
                    <pre className="text-xs overflow-auto max-h-96 p-4 bg-muted rounded-md">{JSON.stringify(analysis, null, 2)}</pre>
                </CardContent>
                </Card>
            )}
          </div>
        )}
      </CardContent>
      <CardFooter className="bg-muted/50">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Info className="h-3 w-3" />
          <p> AI analysis is for informational purposes only and does not constitute financial advice. </p>
        </div>
      </CardFooter>
    </Card>
  );
}
