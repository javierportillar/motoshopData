import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  header?: ReactNode;
  footer?: ReactNode;
  className?: string;
}

export function Card({
  children,
  header,
  footer,
  className = "",
}: CardProps): JSX.Element {
  return (
    <div
      className={`overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm transition-shadow hover:shadow-md ${className}`}
    >
      {header && (
        <div className="border-b border-gray-100 px-4 py-3">{header}</div>
      )}
      <div className="p-4">{children}</div>
      {footer && (
        <div className="border-t border-gray-100 px-4 py-3">{footer}</div>
      )}
    </div>
  );
}
