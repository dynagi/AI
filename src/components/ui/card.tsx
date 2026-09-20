import * as React from "react";
import { cn } from "@/lib/utils";

// A "Card" is a classic Windows window: grey body, 2px black border, hard pixel shadow.
export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("retro-window text-card-foreground", className)} {...props} />
));
Card.displayName = "Card";

// CardHeader is the lavender title bar.
export const CardHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("retro-titlebar", className)} {...props} />
);

export const CardTitle = ({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) => (
  <h3 className={cn("font-pixel text-[13px] font-semibold uppercase tracking-wider text-black", className)} {...props} />
);

export const CardContent = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("p-4", className)} {...props} />
);
