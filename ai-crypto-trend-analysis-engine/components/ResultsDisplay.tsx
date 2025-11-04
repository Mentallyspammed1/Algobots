
import React from 'react';
import { AnalysisResult } from '../types';
import SignalCard from './SignalCard';

interface ResultsDisplayProps {
  results: AnalysisResult[];
  isLoading: boolean;
}

const LoadingSkeleton: React.FC = () => (
    <div className="bg-gray-800/50 p-6 rounded-xl animate-pulse">
        <div className="flex justify-between items-center mb-4">
            <div className="h-8 w-1/3 bg-gray-700 rounded"></div>
            <div className="h-8 w-1/4 bg-gray-700 rounded"></div>
        </div>
        <div className="h-48 bg-gray-700 rounded mb-4"></div>
        <div className="space-y-3">
            <div className="h-4 bg-gray-700 rounded"></div>
            <div className="h-4 bg-gray-700 rounded w-5/6"></div>
            <div className="h-4 bg-gray-700 rounded w-3/4"></div>
        </div>
    </div>
);


const ResultsDisplay: React.FC<ResultsDisplayProps> = ({ results, isLoading }) => {
  return (
    <div className="mt-8">
      <h2 className="text-2xl font-bold mb-4 text-gray-300">Analysis History</h2>
      
      <div className="space-y-6">
        {isLoading && results.length === 0 && <LoadingSkeleton />}
        
        {results.length === 0 && !isLoading && (
          <div className="text-center py-16 px-6 bg-gray-800/50 border border-dashed border-gray-700 rounded-xl">
            <svg className="mx-auto h-12 w-12 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h3 className="mt-2 text-xl font-medium text-gray-300">No analysis run yet</h3>
            <p className="mt-1 text-gray-500">Configure your analysis above and click "Run Analysis" to see the results.</p>
          </div>
        )}

        {results.map((result) => (
          <SignalCard key={result.id} result={result} />
        ))}
      </div>
    </div>
  );
};

export default ResultsDisplay;
