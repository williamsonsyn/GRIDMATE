import type { UiError } from '../hooks/useSimulation';

interface Props { error: UiError; onRetry: () => void; onDismiss: () => void }

const TITLE: Record<UiError['kind'], string> = {
  unavailable: 'API unavailable',
  validation: 'Invalid scenario',
  pipeline: 'Optimization failed',
  unknown: 'Something went wrong',
};

export function Notice({ error, onRetry, onDismiss }: Props) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-red-200 bg-red-50 p-4 text-sm text-red-900">
      <div>
        <p className="font-semibold">{TITLE[error.kind]}</p>
        <p className="mt-0.5">{error.message}</p>
      </div>
      <div className="flex gap-2">
        <button type="button" onClick={onRetry} className="btn bg-red-700 text-white hover:bg-red-800">Try again</button>
        <button type="button" onClick={onDismiss} className="btn border border-red-300 hover:bg-red-100">Dismiss</button>
      </div>
    </div>
  );
}
