const HOST = "artodownloader";
const bypass = new Set(); // Uygulama başarısız olursa tarayıcının kendi indirmesine izin verilen URL'ler

async function cookieHeader(url) {
  try {
    const cookies = await browser.cookies.getAll({ url });
    return cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch (e) {
    return "";
  }
}

browser.downloads.onCreated.addListener(async (item) => {
  const url = item.finalUrl || item.url;
  if (!/^https?:/i.test(url)) return; // blob:, data: vb. atla
  if (bypass.has(item.url)) {
    bypass.delete(item.url);
    return;
  }

  // Tarayıcının kendi indirmesini iptal et
  try {
    await browser.downloads.cancel(item.id);
    await browser.downloads.erase({ id: item.id });
  } catch (e) {}

  const msg = {
    url,
    referrer: item.referrer || "",
    filename: (item.filename || "").split(/[\\/]/).pop(),
    cookie: await cookieHeader(url),
    userAgent: navigator.userAgent,
  };

  try {
    const res = await browser.runtime.sendNativeMessage(HOST, msg);
    if (!res || !res.ok) throw new Error(res && res.error);
  } catch (e) {
    console.error("ArtoDownloader host hatası, tarayıcı indirmesine dönülüyor:", e);
    bypass.add(item.url);
    browser.downloads.download({ url: item.url });
  }
});
