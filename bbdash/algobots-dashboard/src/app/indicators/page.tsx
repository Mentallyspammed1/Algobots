import { defaultIndicatorSettings } from '@/lib/indicators';

export default function IndicatorsPage() {
  return (
    <pre>{JSON.stringify(defaultIndicatorSettings, null, 2)}</pre>
  );
}
