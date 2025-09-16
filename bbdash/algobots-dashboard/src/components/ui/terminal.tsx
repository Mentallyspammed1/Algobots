'use client';

import { Terminal as TerminalIcon } from "lucide-react"
import { cn } from "@/lib/utils";

interface TerminalProps {
    text: string;
    className?: string;
}

export function Terminal({ text, className }: TerminalProps) {
    return (
        <div className={cn("bg-terminal border rounded-lg p-4 text-sm font-mono text-foreground/80 overflow-x-auto", className)}>
            <div className="flex items-center gap-2 pb-2 mb-2 border-b border-gray-700">
                <TerminalIcon className="h-4 w-4" />
                <h5 className="font-semibold">AI Analysis</h5>
            </div>
            <pre className="whitespace-pre-wrap font-code">
                {text}
                <span className="inline-block w-2 h-4 bg-green-400 animate-pulse ml-1" aria-hidden="true"></span>
            </pre>
        </div>
    )
}
