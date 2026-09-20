import * as React from "react";
import { cn } from "@/lib/utils";

// Sunken white edit field, like a classic Windows text box.
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, type, ...props }, ref) => (
  <input
    type={type}
    ref={ref}
    className={cn(
      "retro-sunken flex h-9 w-full px-2 font-mono text-sm text-black placeholder:text-black/50 disabled:opacity-60",
      className,
    )}
    {...props}
  />
));
Input.displayName = "Input";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(({ className, ...props }, ref) => (
  <select ref={ref} className={cn("retro-sunken flex h-9 w-full px-1.5 font-mono text-sm text-black disabled:opacity-60", className)} {...props} />
));
Select.displayName = "Select";

export const Label = ({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => (
  <label className={cn("text-xs font-semibold text-black", className)} {...props} />
);
