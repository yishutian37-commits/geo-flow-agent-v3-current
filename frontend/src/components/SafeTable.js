import React, { useMemo } from 'react';
import { Table as AntTable } from 'antd';

const isActionColumn = (column) => (
  column?.key === 'action'
  || column?.key === 'actions'
  || column?.dataIndex === 'action'
  || column?.dataIndex === 'actions'
  || column?.title === '操作'
);

const textOf = (value) => {
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return String(value);
  return '';
};

const columnIdentity = (column) => [
  textOf(column?.title),
  Array.isArray(column?.dataIndex) ? column.dataIndex.join('_') : textOf(column?.dataIndex),
  textOf(column?.key),
].filter(Boolean).join(' ').toLowerCase();

const getMetaColumnConfig = (column) => {
  const identity = columnIdentity(column);
  if (!identity) return null;

  if (/截止日期|due_?date|日期|date/.test(identity) && !/time|时间|created|updated|started|published/.test(identity)) {
    return { width: 132, className: 'geo-table-nowrap-cell' };
  }
  if (/创建时间|更新时间|开始时间|检测时间|发布时间|created|updated|started|published|detected|time/.test(identity)) {
    return { width: 184, className: 'geo-table-nowrap-cell' };
  }
  if (/状态|status/.test(identity)) {
    return { width: 118, className: 'geo-table-nowrap-cell' };
  }
  if (/优先级|priority/.test(identity)) {
    return { width: 110, className: 'geo-table-nowrap-cell' };
  }
  if (/风险|risk/.test(identity)) {
    return { width: 110, className: 'geo-table-nowrap-cell' };
  }
  if (/版本|version|draft_version/.test(identity)) {
    return { width: 96, className: 'geo-table-nowrap-cell' };
  }
  if (/平台|platform/.test(identity)) {
    return { width: 132, className: 'geo-table-nowrap-cell' };
  }
  if (/链接|link|url/.test(identity)) {
    return { width: 112, className: 'geo-table-nowrap-cell' };
  }
  if (/层级|layer/.test(identity)) {
    return { width: 142, className: 'geo-table-nowrap-cell' };
  }
  if (/来源|source/.test(identity)) {
    return { width: 160, className: 'geo-table-nowrap-cell' };
  }
  if (/推荐状态|情绪|sentiment|信息来源/.test(identity)) {
    return { width: 132, className: 'geo-table-nowrap-cell' };
  }
  if (/内容类型|事实类型|账号类型|来源类型|信源类型|content_type|fact_type|account_type|source_type|change_type/.test(identity)) {
    return { width: 136, className: 'geo-table-nowrap-cell' };
  }
  return null;
};

const normalizeColumns = (columns = []) => columns.map((column) => {
  const normalized = column.children
    ? { ...column, children: normalizeColumns(column.children) }
    : { ...column };

  if (isActionColumn(normalized)) {
    return {
      ...normalized,
      align: normalized.align || 'left',
      className: ['geo-table-action-cell', normalized.className].filter(Boolean).join(' '),
      fixed: normalized.fixed || 'right',
      width: normalized.width || 240,
    };
  }

  const metaConfig = getMetaColumnConfig(normalized);
  if (!metaConfig) return normalized;

  return {
    ...normalized,
    className: [metaConfig.className, normalized.className].filter(Boolean).join(' '),
    width: normalized.width || metaConfig.width,
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
