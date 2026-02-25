"use client";

import { useMemo, useState } from "react";
import type { ReactNode } from "react";

type Column<T> = {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  sortable?: boolean;
  getSortValue?: (row: T) => string | number | boolean | null | undefined;
  getSearchValue?: (row: T) => string;
};

type DataTableProps<T> = {
  columns: Column<T>[];
  rows: T[];
  emptyText?: string;
  enableControls?: boolean;
};

type SortDirection = "asc" | "desc";

function normalizeSortValue(value: string | number | boolean | null | undefined): string | number {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value === "number") return value;
  return value.toString().toLowerCase();
}

export function DataTable<T>({
  columns,
  rows,
  emptyText = "No data",
  enableControls = false,
}: DataTableProps<T>) {
  const sortableColumns = useMemo(
    () => columns.filter((column) => column.sortable !== false),
    [columns],
  );

  const [searchQuery, setSearchQuery] = useState("");
  const [sortKey, setSortKey] = useState<string>(sortableColumns[0]?.key ?? "");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [pageSize, setPageSize] = useState(25);
  const [page, setPage] = useState(1);

  const effectiveSortKey = useMemo(() => {
    return sortableColumns.some((column) => column.key === sortKey)
      ? sortKey
      : (sortableColumns[0]?.key ?? "");
  }, [sortableColumns, sortKey]);

  const filteredRows = useMemo(() => {
    if (!enableControls) return rows;

    const normalizedQuery = searchQuery.trim().toLowerCase();
    if (!normalizedQuery) return rows;

    return rows.filter((row) =>
      columns.some((column) => {
        const explicitSearch = column.getSearchValue?.(row);
        if (explicitSearch !== undefined) {
          return explicitSearch.toLowerCase().includes(normalizedQuery);
        }

        const sortSource = column.getSortValue?.(row);
        if (sortSource !== undefined && sortSource !== null) {
          return sortSource.toString().toLowerCase().includes(normalizedQuery);
        }

        return false;
      }),
    );
  }, [enableControls, searchQuery, rows, columns]);

  const sortedRows = useMemo(() => {
    if (!enableControls || !effectiveSortKey) return filteredRows;

    const sortColumn = columns.find((column) => column.key === effectiveSortKey);
    if (!sortColumn || sortColumn.sortable === false || !sortColumn.getSortValue) {
      return filteredRows;
    }

    const sorted = [...filteredRows].sort((a, b) => {
      const aValue = normalizeSortValue(sortColumn.getSortValue?.(a));
      const bValue = normalizeSortValue(sortColumn.getSortValue?.(b));

      if (typeof aValue === "number" && typeof bValue === "number") {
        return aValue - bValue;
      }

      return aValue.toString().localeCompare(bValue.toString(), undefined, {
        numeric: true,
        sensitivity: "base",
      });
    });

    return sortDirection === "asc" ? sorted : sorted.reverse();
  }, [enableControls, effectiveSortKey, sortDirection, filteredRows, columns]);

  const totalRows = sortedRows.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));
  const currentPage = enableControls ? Math.min(page, totalPages) : 1;

  const paginatedRows = useMemo(() => {
    if (!enableControls) return sortedRows;
    const start = (currentPage - 1) * pageSize;
    return sortedRows.slice(start, start + pageSize);
  }, [enableControls, sortedRows, currentPage, pageSize]);

  const handleSort = (column: Column<T>) => {
    if (!enableControls || column.sortable === false) return;
    if (!column.getSortValue) return;

    if (effectiveSortKey === column.key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }

    setSortKey(column.key);
    setSortDirection("asc");
    setPage(1);
  };

  return (
    <div className="space-y-3">
      {enableControls && (
        <div className="glass-soft flex flex-col gap-2 rounded-xl p-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative w-full sm:max-w-xs">
            <input
              value={searchQuery}
              onChange={(event) => {
                setSearchQuery(event.target.value);
                setPage(1);
              }}
              placeholder="Search in current table"
              className="glass-input glass-focus w-full rounded-xl px-3 py-2 pr-9 text-sm"
              aria-label="Search in current table"
            />
            {searchQuery.trim().length > 0 && (
              <button
                type="button"
                onClick={() => {
                  setSearchQuery("");
                  setPage(1);
                }}
                aria-label="Clear search"
                title="Clear search"
                className="glass-btn-secondary glass-focus absolute top-1/2 right-1 inline-flex h-7 w-7 -translate-y-1/2 cursor-pointer items-center justify-center rounded-lg text-sm"
              >
                ×
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <label className="glass-muted text-xs uppercase tracking-wide" htmlFor="rows-per-page">
              Rows
            </label>
            <select
              id="rows-per-page"
              value={pageSize}
              onChange={(event) => {
                setPageSize(Number(event.target.value));
                setPage(1);
              }}
              className="glass-input glass-focus rounded-xl px-2 py-1.5 text-sm"
            >
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>
        </div>
      )}

      <div className="glass-table overflow-x-auto rounded-2xl">
        <table className="min-w-full text-left text-sm">
          <thead className="glass-muted glass-soft">
            <tr>
              {columns.map((column) => {
                const isSortable = enableControls && column.sortable !== false && Boolean(column.getSortValue);
                const isActiveSort = effectiveSortKey === column.key;
                const sortMarker = isActiveSort ? (sortDirection === "asc" ? "↑" : "↓") : "↕";

                return (
                  <th key={column.key} className="px-4 py-3 font-semibold tracking-wide">
                    {isSortable ? (
                      <button
                        type="button"
                        onClick={() => handleSort(column)}
                        className="glass-focus inline-flex cursor-pointer items-center gap-1 rounded-md"
                      >
                        <span>{column.header}</span>
                        <span aria-hidden="true" className="inline-flex w-4 justify-center tabular-nums">
                          {sortMarker}
                        </span>
                      </button>
                    ) : (
                      <span>{column.header}</span>
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {paginatedRows.length === 0 ? (
              <tr>
                <td className="glass-muted px-4 py-8" colSpan={columns.length}>
                  {emptyText}
                </td>
              </tr>
            ) : (
              paginatedRows.map((row, index) => (
                <tr key={index} className="border-t border-[var(--glass-soft-border)] transition-colors hover:bg-[var(--glass-soft-bg)]">
                  {columns.map((column) => (
                    <td key={column.key} className="glass-title px-4 py-3 align-top">
                      {column.render(row)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {enableControls && (
        <div className="flex flex-col gap-2 text-xs sm:flex-row sm:items-center sm:justify-between">
          <p className="glass-muted">
            Showing {totalRows === 0 ? 0 : (currentPage - 1) * pageSize + 1}
            –{Math.min(currentPage * pageSize, totalRows)} of {totalRows}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              disabled={currentPage <= 1}
              className="glass-btn-secondary glass-focus cursor-pointer rounded-lg px-2.5 py-1.5 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Prev
            </button>
            <span className="glass-muted">Page {currentPage} / {totalPages}</span>
            <button
              type="button"
              onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
              disabled={currentPage >= totalPages}
              className="glass-btn-secondary glass-focus cursor-pointer rounded-lg px-2.5 py-1.5 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
