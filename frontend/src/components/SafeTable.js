import React, { useMemo } from 'react';
import { Table as AntTable } from 'antd';

const isActionColumn = (column) => (
  column?.key === 'action'
  || column?.dataIndex === 'action'
  || column?.title === '操作'
);

const normalizeColumns = (columns = []) => columns.map((column) => {
  const normalized = column.children
    ? { ...column, children: normalizeColumns(column.children) }
    : { ...column };

  if (!isActionColumn(normalized)) return normalized;

  return {
    ...normalized,
    align: normalized.align || 'left',
    className: ['geo-table-action-cell', normalized.className].filter(Boolean).join(' '),
    fixed: normalized.fixed || 'right',
    width: normalized.width || 240,
  };
});

function SafeTable({
  columns,
  scroll,
  tableLayout = 'fixed',
  className,
  ...props
}) {
  const safeColumns = useMemo(() => normalizeColumns(columns), [columns]);

  return (
    <div className="geo-safe-table">
      <AntTable
        {...props}
        className={['geo-table', className].filter(Boolean).join(' ')}
        columns={safeColumns}
        scroll={{ x: 'max-content', ...(scroll || {}) }}
        tableLayout={tableLayout}
      />
    </div>
  );
}

export default SafeTable;
