import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface Column<T> {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  align?: "left" | "right";
  /** Hide on narrower laptop screens to keep the rest readable. */
  wideOnly?: boolean;
  className?: string;
}

/**
 * A data table for laptop screens: full width, sticky header, whole-row click, columns that can
 * drop away on narrower screens. Phones use card lists instead.
 */
export function DataTable<T>({ rows, columns, rowKey, onRowClick, rowClassName, caption }: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  rowClassName?: (row: T) => string | undefined;
  caption?: string;
}) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-line bg-surface shadow-card">
      <table className="w-full border-collapse text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="sticky top-0 z-[1] bg-sunken text-left">
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col"
                className={cn("whitespace-nowrap px-4 py-3 font-semibold text-muted", c.align === "right" && "text-right",
                  c.wideOnly && "hidden 2xl:table-cell", c.className)}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cn("border-t border-line", onRowClick && "cursor-pointer hover:bg-sunken/70", rowClassName?.(row))}>
              {columns.map((c) => (
                <td key={c.key}
                  className={cn("px-4 py-3 align-middle", c.align === "right" && "text-right tabular",
                    c.wideOnly && "hidden 2xl:table-cell", c.className)}>
                  {c.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
