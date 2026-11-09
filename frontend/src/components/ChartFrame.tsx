import type { EChartsCoreOption } from 'echarts/core';
import type { ReactNode } from 'react';
import { useEChart } from '../hooks/useEChart';

interface Props {
  title: string;
  caption?: string;
  option: EChartsCoreOption | null;
  height?: number;
  busy?: boolean;
  empty?: ReactNode;
}

/** Shared panel + chart canvas used by every chart component. */
export function ChartFrame({ title, caption, option, height = 280, busy = false, empty }: Props) {
  const ref = useEChart(option);
  return (
    <section className="panel p-4" aria-label={title} aria-busy={busy}>
      <div className="mb-2">
        <h3 className="font-display text-base font-semibold">{title}</h3>
        {caption && <p className="text-xs text-ink-mute">{caption}</p>}
      </div>
      <div className="relative">
        <div ref={ref} style={{ height }} className={busy ? 'opacity-40 transition-opacity' : 'transition-opacity'} />
        {!option && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-ink-mute">
            {empty ?? 'No data to display.'}
          </div>
        )}
      </div>
    </section>
  );
}
