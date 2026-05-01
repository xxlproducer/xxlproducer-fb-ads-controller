import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, hint, error, className, id, ...rest }, ref) => {
    const inputId = id ?? rest.name;
    return (
      <label htmlFor={inputId} className="block">
        {label && (
          <span className="mb-1.5 block text-sm font-medium text-ink-700 dark:text-ink-300">
            {label}
          </span>
        )}
        <input
          id={inputId}
          ref={ref}
          className={cn(
            "block w-full rounded-xl border bg-white px-3.5 py-2.5 text-sm",
            "border-ink-200 dark:border-ink-700 dark:bg-ink-800",
            "placeholder:text-ink-400 dark:placeholder:text-ink-500",
            "focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent",
            "transition-shadow duration-150",
            error && "border-danger focus:ring-danger/20 focus:border-danger",
            className,
          )}
          {...rest}
        />
        {(hint || error) && (
          <span
            className={cn(
              "mt-1.5 block text-xs",
              error ? "text-danger" : "text-ink-500",
            )}
          >
            {error || hint}
          </span>
        )}
      </label>
    );
  },
);
Input.displayName = "Input";
