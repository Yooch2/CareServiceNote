import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

const BUTTON = {
  primary: "bg-pine text-white hover:bg-pine-dark disabled:bg-line disabled:text-muted",
  secondary: "bg-sheet text-ink border border-line hover:border-pine disabled:text-muted",
  ghost: "text-muted hover:text-ink hover:bg-sheet",
  danger: "bg-sheet text-risk border border-line hover:border-risk",
};

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof BUTTON }) {
  return (
    <button
      type="button"
      className={`inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-5 font-semibold transition-colors disabled:cursor-not-allowed ${BUTTON[variant]} ${className}`}
      {...props}
    />
  );
}

/** 종이 한 장. 그림자 없이 가는 선으로만 구분한다. */
export function Sheet({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-lg border border-line bg-sheet p-4 ${className}`}>{children}</div>;
}

const TONE = {
  neutral: "bg-paper text-muted border-line",
  remark: "bg-remark/10 text-remark border-remark/30",
  observe: "bg-observe/10 text-observe border-observe/30",
  follow: "bg-follow/10 text-follow border-follow/30",
  risk: "bg-risk/10 text-risk border-risk/40",
  pine: "bg-pine/10 text-pine border-pine/30",
};
export type Tone = keyof typeof TONE;

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-sm font-medium ${TONE[tone]}`}>
      {children}
    </span>
  );
}

export function Field({ label, hint, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return (
    <label className="flex flex-col gap-1.5 font-medium">
      {label}
      <input
        className="min-h-12 rounded-xl border border-line bg-sheet px-4 font-normal focus:border-pine focus:outline-none"
        {...props}
      />
      {hint && <span className="text-sm font-normal text-muted">{hint}</span>}
    </label>
  );
}

export function PageTitle({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="mb-5">
      <h1 className="text-[1.75rem] leading-tight font-bold">{children}</h1>
      {sub && <div className="mt-1.5 text-muted">{sub}</div>}
    </div>
  );
}

const NOTICE = {
  info: "border-pine bg-pine/5",
  warn: "border-follow bg-follow/5",
  error: "border-risk bg-risk/5",
};

export function Notice({ tone = "info", children }: { tone?: keyof typeof NOTICE; children: ReactNode }) {
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`rounded-r-lg border-l-4 px-4 py-3 ${NOTICE[tone]}`}>
      {children}
    </div>
  );
}

export function Loading() {
  return <p className="py-10 text-center text-muted">불러오는 중…</p>;
}
