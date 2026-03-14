export function StatusBadge({ source, isTelegram }: { source: 'api' | 'mock'; isTelegram: boolean }) {
  return (
    <div className="status-badge-wrap">
      <span className={source === 'api' ? 'status-badge is-live' : 'status-badge'}>
        {source === 'api' ? 'Live API' : 'Mock data'}
      </span>
      <span className="status-badge">{isTelegram ? 'Telegram WebApp' : 'Browser preview'}</span>
    </div>
  )
}
