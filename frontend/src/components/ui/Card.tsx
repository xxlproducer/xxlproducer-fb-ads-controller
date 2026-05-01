import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-2xl bg-white shadow-card dark:bg-ink-800/60 dark:shadow-none dark:ring-1 dark:ring-ink-700/60",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  description,
  action,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 border-b border-ink-100 px-6 py-5 dark:border-ink-700",
        className,
      )}
    >
      <div className="min-w-0">
        <h3 className="text-base font-semibold tracking-tight text-ink-900 dark:text-ink-100">
          {title}
        </h3>
        {description && (
          <p className="mt-1 text-sm text-ink-500">{description}</p>
        )}
      </div>
      {action && <div className="flex-shrink-0">{action}</div>}
    </div>
  );
}

export function CardBody({ className, children }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-6", className)}>{children}</div>;
}
