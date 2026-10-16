import { useState } from "react";
import { flexRender, getCoreRowModel, getSortedRowModel, useReactTable } from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { cn } from "./ui";

/** Bảng có sắp xếp (TanStack Table v8). columns: định nghĩa cột chuẩn, meta.align = "r" để căn phải. */
export function DataTable({ data, columns, initialSort, minWidth = 560, getRowId, empty = "Không có dữ liệu." }) {
  const [sorting, setSorting] = useState(initialSort || []);
  const table = useReactTable({
    data, columns, state: { sorting }, onSortingChange: setSorting, getRowId,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(),
  });
  return (
    <div className="scroll-x">
      <table className="tbl" style={{ minWidth }}>
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => {
                const s = h.column.getIsSorted();
                const can = h.column.getCanSort();
                return (
                  <th key={h.id} className={h.column.columnDef.meta?.align === "r" ? "r" : ""} aria-sort={s === "asc" ? "ascending" : s === "desc" ? "descending" : "none"}>
                    {can ? (
                      <button type="button" onClick={h.column.getToggleSortingHandler()} title="Bấm để sắp xếp">
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        {s === "asc" ? <ArrowUp size={12} /> : s === "desc" ? <ArrowDown size={12} /> : <ChevronsUpDown size={12} className="opacity-40" />}
                      </button>
                    ) : flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((r) => (
            <tr key={r.id}>
              {r.getVisibleCells().map((c) => (
                <td key={c.id} className={cn(c.column.columnDef.meta?.align === "r" && "r")}>{flexRender(c.column.columnDef.cell, c.getContext())}</td>
              ))}
            </tr>
          ))}
          {!data.length && <tr><td colSpan={columns.length} className="text-muted">{empty}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
