'use client';

import { CandlestickChart, ChevronsUpDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { SYMBOLS, TIME_FRAMES } from '@/lib/constants';
import { ThemeToggle } from '@/components/ui/theme-toggle';

interface DashboardHeaderProps {
  symbol: string;
  setSymbol: (symbol: string) => void;
  timeframe: string;
  setTimeframe: (timeframe: string) => void;
}

export function DashboardHeader({ symbol, setSymbol, timeframe, setTimeframe }: DashboardHeaderProps) {
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 px-4 md:px-6">
      <div className="flex items-center gap-2">
        <CandlestickChart className="h-6 w-6 text-primary" />
        <h1 className="text-xl font-bold tracking-tight">Bybit Edge</h1>
      </div>
      <div className="flex items-center gap-4 ml-auto">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" className="w-[140px] justify-between">
              {symbol}
              <ChevronsUpDown className="h-4 w-4 opacity-50" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-[140px]">
            {SYMBOLS.map((s) => (
              <DropdownMenuItem key={s} onSelect={() => setSymbol(s)}>
                {s}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" className="w-[100px] justify-between">
              {timeframe}
              <ChevronsUpDown className="h-4 w-4 opacity-50" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-[100px]">
            {TIME_FRAMES.map((t) => (
              <DropdownMenuItem key={t} onSelect={() => setTimeframe(t)}>
                {t}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <ThemeToggle />
      </div>
    </header>
  );
}
