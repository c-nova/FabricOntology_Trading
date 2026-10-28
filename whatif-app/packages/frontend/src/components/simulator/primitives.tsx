import { CircleAlert, LoaderCircle } from 'lucide-react';
import type { ReactNode } from 'react';

import type { Explained } from '@/lib/errors';
import { cn } from '@/lib/utils';

// 区切りの見出し。帳簿の項目名のように、小さく、字間を空ける。
export function SectionLabel({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <h2 id={id} className="font-base text-200 font-semibold tracking-widest text-muted-foreground">
      {children}
    </h2>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-200 text-300 text-muted-foreground">
      <LoaderCircle aria-hidden className="icon-size-200 animate-spin" />
      {label}
    </span>
  );
}

// 取得の失敗。人が取る行動を示し、内部の識別子は出さない。
export function ErrorNotice({ error, onRetry, className }: { error: Explained; onRetry?: () => void; className?: string }) {
  return (
    <div role="alert" className={cn('flex gap-300 rounded-lg border border-destructive bg-card p-400', className)}>
      <CircleAlert aria-hidden className="icon-size-300 mt-100 shrink-0 text-destructive" />
      <div className="min-w-0 space-y-200">
        <p className="text-400 font-semibold text-destructive">{error.title}</p>
        <p className="text-300 text-foreground">{error.action}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="h-control rounded-md border border-input bg-card px-400 text-300 font-medium text-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            再試行
          </button>
        )}
      </div>
    </div>
  );
}

// 骨組み。読み込み中の場所に、完成後と同じ大きさで置く。
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn('animate-pulse rounded-md bg-muted', className)} />;
}

export type Tone = 'negative' | 'positive' | 'neutral';

// 小さな札。意味は文字でも伝える（色だけに頼らない）。
export function Chip({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  const style =
    tone === 'negative'
      ? 'border-destructive text-destructive'
      : tone === 'positive'
        ? 'border-brand-foreground text-brand-foreground'
        : 'border-border text-muted-foreground';
  return <span className={`inline-flex items-center rounded-sm border px-200 py-100-nudge text-200 font-medium ${style}`}>{children}</span>;
}

export interface SegmentedOption<T extends string> {
  id: T;
  label: string;
  title?: string;
}

// 切り替え（ラジオ）。ネイティブの radio を使うので、矢印キーでの移動は標準の動作になる。
export function Segmented<T extends string>({
  legend,
  name,
  value,
  options,
  onChange,
}: {
  legend: string;
  name: string;
  value: T;
  options: readonly SegmentedOption<T>[];
  onChange: (id: T) => void;
}) {
  return (
    <fieldset className="inline-flex rounded-md border border-input bg-muted p-100">
      <legend className="sr-only">{legend}</legend>
      {options.map((o) => (
        <label key={o.id} title={o.title} className="relative cursor-pointer">
          <input type="radio" name={name} value={o.id} checked={value === o.id} onChange={() => onChange(o.id)} className="peer sr-only" />
          <span className="flex h-control items-center rounded-sm px-400 text-300 font-medium text-foreground peer-checked:bg-primary peer-checked:text-primary-foreground peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-ring">
            {o.label}
          </span>
        </label>
      ))}
    </fieldset>
  );
}
