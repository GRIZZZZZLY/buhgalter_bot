export function StatusBadge({ source, isTelegram }: { source: 'api' | 'mock'; isTelegram: boolean }) {
  return (
    <div className="status-badge-wrap">
      <span className={source === 'api' ? 'status-badge is-live' : 'status-badge'}>
        <span className="status-badge__glyph">✦</span>
        {source === 'api' ? 'Live API' : 'Mock data'}
      </span>
      <span className="status-badge">
        <span className="status-badge__glyph">◌</span>
        {isTelegram ? 'Telegram WebApp' : 'Browser preview'}
      </span>
    </div>
  )
}
