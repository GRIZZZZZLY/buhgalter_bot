import WebApp from '@twa-dev/sdk'

export function initTelegramWebApp() {
  try {
    WebApp.ready()
    WebApp.expand()
    WebApp.setHeaderColor('#f6efe1')
    WebApp.setBackgroundColor('#f6efe1')
  } catch {
    // ignore outside telegram
  }

  return {
    user: WebApp.initDataUnsafe?.user ?? null,
    colorScheme: WebApp.colorScheme ?? 'light',
    isTelegram: Boolean(WebApp.initDataUnsafe),
    webApp: WebApp,
  }
}
