export default function LoadingState({ compact = false }) {
  return (
    <div
      role="status"
      aria-label="正在加载"
      style={{
        position: compact ? 'relative' : 'fixed',
        inset: compact ? undefined : 0,
        width: compact ? '100%' : '100vw',
        height: compact ? '100%' : '100dvh',
        minHeight: compact ? 180 : undefined,
        display: 'grid',
        placeItems: 'center',
        background: compact ? 'transparent' : '#e8d5b0',
        color: '#574b35',
        fontFamily: 'inherit',
        zIndex: compact ? undefined : 100,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 24 }}>
        <span
          className="app-loading-spinner"
          aria-hidden="true"
          style={{
            display: 'block',
            width: 22,
            height: 22,
            boxSizing: 'border-box',
            border: '2px solid #cdbc96',
            borderTopColor: '#574b35',
            borderRadius: '50%',
          }}
        />
        <span style={{ fontSize: 14, fontWeight: 600 }}>正在载入工作区</span>
      </div>
    </div>
  );
}
